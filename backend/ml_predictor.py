"""
ML prediction engine for StockIQ.

Two models run on every ticker:
  1. XGBoost  — snapshot features (RSI, momentum, MA crossovers, etc.)
  2. LSTM     — 60-day price sequence (learns temporal patterns)

Their probabilities are ensembled (weighted average) to produce the
final 30-day directional forecast + price target range.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import yfinance as yf
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from transformers import pipeline as hf_pipeline
from dotenv import load_dotenv

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Constants ─────────────────────────────────────────────────────────────────

LOOKBACK  = 60   # days of history fed into the LSTM per prediction
HORIZON   = 30   # days ahead we're trying to predict

# XGBoost snapshot features
XGB_FEATURES = [
    "ret_1d", "ret_5d", "ret_10d", "ret_20d",
    "vol_20d", "rsi_norm", "macd_norm", "macd_hist_norm",
    "price_vs_ma50", "price_vs_ma200", "ma50_vs_ma200",
    "vol_ratio", "hl_range",
]

# LSTM sequence features (per timestep)
LSTM_FEATURES = [
    "ret_1d", "ret_5d", "rsi_norm",
    "macd_hist_norm", "vol_ratio", "hl_range",
]

FEATURE_LABELS = {
    "ret_1d":          "1-day momentum",
    "ret_5d":          "5-day momentum",
    "ret_10d":         "10-day momentum",
    "ret_20d":         "20-day momentum",
    "vol_20d":         "Volatility (20d)",
    "rsi_norm":        "RSI signal",
    "macd_norm":       "MACD level",
    "macd_hist_norm":  "MACD histogram",
    "price_vs_ma50":   "Price vs MA50",
    "price_vs_ma200":  "Price vs MA200",
    "ma50_vs_ma200":   "Golden/Death cross",
    "vol_ratio":       "Volume surge",
    "hl_range":        "Daily price range",
}

# Ensemble weights
XGB_WEIGHT  = 0.45
LSTM_WEIGHT = 0.35
SENT_WEIGHT = 0.20   # news sentiment as a third model signal


# ── LSTM model definition ─────────────────────────────────────────────────────

class LSTMNet(nn.Module):
    """
    Two-layer LSTM that reads a window of daily features and outputs
    a logit (pre-sigmoid score) for BCEWithLogitsLoss during training,
    or a probability after sigmoid during inference.

    Shape flow:
      input  → (batch, LOOKBACK, n_features)
      lstm   → (batch, LOOKBACK, hidden)  — keep only the last step
      linear → (batch, 1)  → scalar logit per sample
    """
    def __init__(self, n_features: int, hidden: int = 64, layers: int = 2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden,
            num_layers=layers,
            batch_first=True,
            dropout=0.15,             # light dropout between LSTM layers only
        )
        self.norm = nn.LayerNorm(hidden)
        self.head = nn.Sequential(
            nn.Linear(hidden, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)          # (batch, seq, hidden)
        last   = self.norm(out[:, -1, :])
        return self.head(last).squeeze(1)  # logit


# ── Feature engineering (shared by both models) ───────────────────────────────

def _compute_features(hist: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all features. MA window lengths adapt to available history:
      >= 400 rows → MA50 + MA200  (full feature set)
      >= 220 rows → MA50 only     (drops the two MA200 features)
    """
    n  = len(hist)
    df = hist[["Close", "Volume", "High", "Low"]].copy()

    # Returns
    df["ret_1d"]  = df["Close"].pct_change(1)
    df["ret_5d"]  = df["Close"].pct_change(5)
    df["ret_10d"] = df["Close"].pct_change(10)
    df["ret_20d"] = df["Close"].pct_change(20)
    df["vol_20d"] = df["ret_1d"].rolling(20).std()

    # RSI(14) normalised to [-1, 1]
    delta    = df["Close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    rsi      = 100 - (100 / (1 + rs))
    df["rsi_norm"] = (rsi - 50) / 50

    # MACD (price-normalised)
    ema12  = df["Close"].ewm(span=12, adjust=False).mean()
    ema26  = df["Close"].ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df["macd_norm"]      = macd  / df["Close"]
    df["macd_hist_norm"] = (macd - signal) / df["Close"]

    # MA50 (always computed)
    ma50 = df["Close"].rolling(50).mean()
    df["price_vs_ma50"] = (df["Close"] - ma50) / ma50

    # MA200 only when there's enough history to be meaningful
    if n >= 400:
        ma200 = df["Close"].rolling(200).mean()
        df["price_vs_ma200"] = (df["Close"] - ma200) / ma200
        df["ma50_vs_ma200"]  = (ma50 - ma200) / ma200

    # Volume & range
    vol_avg        = df["Volume"].rolling(20).mean()
    df["vol_ratio"] = df["Volume"] / vol_avg.replace(0, np.nan)
    df["hl_range"]  = (df["High"] - df["Low"]) / df["Close"]

    return df


def _feature_cols_for(df: pd.DataFrame) -> list[str]:
    """Return the XGB feature list that actually exists in this dataframe."""
    return [c for c in XGB_FEATURES if c in df.columns]


# ── XGBoost ───────────────────────────────────────────────────────────────────

def _train_xgboost(df: pd.DataFrame):
    """Train XGBoost on snapshot features, return (model, prob_up, importance)."""
    feat_cols = _feature_cols_for(df)

    df_xgb = df.copy()
    df_xgb["forward_ret"] = df_xgb["Close"].pct_change(HORIZON).shift(-HORIZON)
    df_xgb["label"]       = (df_xgb["forward_ret"] > 0).astype(int)

    train = df_xgb.dropna(subset=feat_cols + ["forward_ret"])
    if len(train) < 80:
        return None, None, None

    X = train[feat_cols].values
    y = train["label"].values

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=5,
        eval_metric="logloss",
        verbosity=0,
        random_state=42,
    )
    model.fit(X, y)

    latest = df[feat_cols].dropna().iloc[[-1]]
    if latest.empty:
        return None, None, None

    prob_up    = float(model.predict_proba(latest)[0][1])
    importance = {f: float(v) for f, v in zip(feat_cols, model.feature_importances_)}

    return model, prob_up, importance


# ── LSTM ──────────────────────────────────────────────────────────────────────

def _build_sequences(df: pd.DataFrame, lookback: int = LOOKBACK):
    """
    Slide a window of `lookback` days across the feature matrix.
    Returns X (n_samples, lookback, n_feat) and y (n_samples,) as numpy arrays.
    The last sequence has no label and is returned separately as `latest_seq`.
    """
    df_lstm = df.copy()
    df_lstm["forward_ret"] = df_lstm["Close"].pct_change(HORIZON).shift(-HORIZON)
    df_lstm["label"]       = (df_lstm["forward_ret"] > 0).astype(int)

    # Drop rows where sequence features are NaN, keep label separately
    feat_df = df_lstm[LSTM_FEATURES].copy()

    # Z-score normalise each feature across the whole history
    means = feat_df.mean()
    stds  = feat_df.std().replace(0, 1)
    feat_norm = (feat_df - means) / stds

    values = feat_norm.values          # (T, n_feat)
    labels = df_lstm["label"].values   # (T,)
    valid  = df_lstm["forward_ret"].notna().values  # rows with a known future label

    X_list, y_list = [], []
    for i in range(lookback, len(values)):
        seq = values[i - lookback : i]
        if np.any(np.isnan(seq)):
            continue
        if valid[i]:                   # has a label → training sample
            X_list.append(seq)
            y_list.append(float(labels[i]))

    # The very last sequence is "today" — used for inference only
    latest_seq = values[-lookback:]
    if np.any(np.isnan(latest_seq)):
        latest_seq = None

    if not X_list:
        return None, None, None

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32), latest_seq


def _train_lstm(df: pd.DataFrame, lookback: int = LOOKBACK, seed: int = 42) -> float | None:
    """
    Train the LSTM and return the probability that today → up in HORIZON days.
    Returns None if there isn't enough data.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    X, y, latest_seq = _build_sequences(df, lookback=lookback)
    if X is None or len(X) < 50 or latest_seq is None:
        return None

    n_features = X.shape[2]

    # ── Class imbalance weight (makes loss equal for both classes) ──
    pos_ratio  = float(y.mean())
    neg_ratio  = 1.0 - pos_ratio
    pos_weight = torch.tensor([neg_ratio / pos_ratio]) if pos_ratio > 0 else torch.tensor([1.0])

    # ── DataLoader ──
    dataset = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    loader  = DataLoader(dataset, batch_size=32, shuffle=True)

    # ── Model, optimizer, loss ──
    device  = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model   = LSTMNet(n_features=n_features).to(device)
    opt     = torch.optim.Adam(model.parameters(), lr=5e-4, weight_decay=1e-4)
    sched   = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight.to(device))

    # ── Training loop ──
    best_loss  = float("inf")
    patience   = 10
    no_improve = 0

    model.train()
    for _ in range(80):
        epoch_loss = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            logits = model(xb)
            loss   = loss_fn(logits, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            epoch_loss += loss.item()

        avg_loss = epoch_loss / len(loader)
        sched.step(avg_loss)

        if avg_loss < best_loss - 1e-4:
            best_loss  = avg_loss
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break

    # ── Inference — convert logit → probability ──
    model.eval()
    with torch.no_grad():
        seq_t = torch.from_numpy(latest_seq.astype(np.float32)).unsqueeze(0).to(device)
        logit = model(seq_t)
        prob  = torch.sigmoid(logit).item()

    return float(prob)


def _train_lstm_ensemble(df: pd.DataFrame, lookback: int = LOOKBACK, n_runs: int = 5) -> tuple[float | None, float | None]:
    """
    Run the LSTM n_runs times with different seeds.
    Returns (mean_prob, std_prob) so the caller can show uncertainty.
    """
    probs = []
    for i in range(n_runs):
        prob = _train_lstm(df, lookback=lookback, seed=42 + i * 13)
        if prob is not None:
            probs.append(prob)
    if not probs:
        return None, None
    return float(np.mean(probs)), float(np.std(probs))


# ── Public API ────────────────────────────────────────────────────────────────

def train_and_predict(ticker: str) -> dict | None:
    """
    Fetch history, train XGBoost + LSTM, ensemble their probabilities.
    Returns a dict ready to be JSON-serialised by FastAPI.
    """
    t    = yf.Ticker(ticker)
    hist = t.history(period="3y")
    hist = hist[hist["Close"].notna()].copy()

    if len(hist) < 150:   # absolute minimum: ~7 months of daily data
        return None

    df = _compute_features(hist)

    # ── Run both models ──
    lookback = min(LOOKBACK, max(20, len(hist) // 5))
    _, xgb_prob, importance       = _train_xgboost(df)
    lstm_prob, lstm_uncertainty   = _train_lstm_ensemble(df, lookback=lookback, n_runs=5)

    if xgb_prob is None:
        return None

    # If LSTM failed, fall back to XGBoost only
    if lstm_prob is None:
        ensemble_prob = xgb_prob
        models_used   = ["XGBoost"]
    else:
        ensemble_prob = XGB_WEIGHT * xgb_prob + LSTM_WEIGHT * lstm_prob
        models_used   = ["XGBoost", "LSTM"]

    direction = "Bullish" if ensemble_prob >= 0.5 else "Bearish"
    raw_conf  = ensemble_prob if ensemble_prob >= 0.5 else (1 - ensemble_prob)

    # ── Price range (volatility-scaled) ──
    current_price = float(hist["Close"].iloc[-1])
    vol_20d_val   = float(df["vol_20d"].dropna().iloc[-1]) if not df["vol_20d"].dropna().empty else 0.015
    expected_move = current_price * vol_20d_val * np.sqrt(HORIZON)

    if direction == "Bullish":
        price_low  = round(current_price - expected_move * 0.5, 2)
        price_high = round(current_price + expected_move, 2)
    else:
        price_low  = round(current_price - expected_move, 2)
        price_high = round(current_price + expected_move * 0.5, 2)

    # ── Top feature signals (from XGBoost) ──
    top_signals = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:6] if importance else []

    return {
        "direction":       direction,
        "confidence":      round(float(raw_conf) * 100, 1),
        "probUp":          round(float(ensemble_prob) * 100, 1),
        "currentPrice":    round(current_price, 2),
        "priceTargetLow":  round(float(max(0.01, price_low)), 2),
        "priceTargetHigh": round(float(price_high), 2),
        "modelsUsed":      models_used,
        "modelBreakdown": {
            "xgboost":         round(float(xgb_prob) * 100, 1),
            "lstm":            round(float(lstm_prob) * 100, 1) if lstm_prob is not None else None,
            "lstmUncertainty": round(float(lstm_uncertainty) * 100, 1) if lstm_uncertainty is not None else None,
            "ensemble":        round(float(ensemble_prob) * 100, 1),
        },
        "topSignals": [
            {"feature": FEATURE_LABELS.get(f, f), "importance": round(float(v) * 100, 1)}
            for f, v in top_signals
        ],
        "horizonDays": HORIZON,
    }


# ── Sentiment ─────────────────────────────────────────────────────────────────

_finbert = None

def _get_finbert():
    global _finbert
    if _finbert is None:
        _finbert = hf_pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device="mps" if __import__("torch").backends.mps.is_available() else -1,
            top_k=None,
        )
    return _finbert


def _score_titles(titles: list[str]) -> list[dict]:
    titles = [t[:512] for t in titles if t]
    if not titles:
        return []
    finbert = _get_finbert()
    raw = finbert(titles)
    results = []
    for title, label_scores in zip(titles, raw):
        scores = {item["label"]: item["score"] for item in label_scores}
        compound = scores.get("positive", 0) - scores.get("negative", 0)
        sentiment = "Positive" if compound > 0.05 else "Negative" if compound < -0.05 else "Neutral"
        results.append({
            "title":     title[:130],
            "score":     round(compound, 3),
            "sentiment": sentiment,
        })
    return results


def _source_summary(items: list[dict]) -> dict:
    scores = [i["score"] for i in items]
    avg    = float(np.mean(scores)) if scores else 0.0
    return {
        "averageScore":  round(avg, 3),
        "label":         "Bullish" if avg > 0.05 else "Bearish" if avg < -0.05 else "Neutral",
        "count":         len(scores),
        "positiveCount": sum(1 for s in scores if s > 0.05),
        "negativeCount": sum(1 for s in scores if s < -0.05),
        "neutralCount":  sum(1 for s in scores if -0.05 <= s <= 0.05),
        "headlines":     items[:8],
    }


def _fetch_yfinance(ticker: str) -> dict:
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        raw = []
    titles = [
        item.get("title") or (item.get("content") or {}).get("title") or ""
        for item in raw[:25]
    ]
    return _source_summary(_score_titles(titles))


def _fetch_newsapi(ticker: str, company_name: str) -> dict | None:
    key = os.getenv("NEWS_API_KEY", "")
    if not key:
        return None
    try:
        from newsapi import NewsApiClient
        client  = NewsApiClient(api_key=key)
        query   = f'"{ticker}" OR "{company_name}"' if company_name else ticker
        resp    = client.get_everything(q=query, language="en", sort_by="publishedAt", page_size=30)
        titles  = [a.get("title", "") or "" for a in (resp.get("articles") or [])]
        return _source_summary(_score_titles(titles))
    except Exception:
        return None


def get_news_sentiment(ticker: str, company_name: str = "") -> dict:
    yf_data      = _fetch_yfinance(ticker)
    newsapi_data = _fetch_newsapi(ticker, company_name)

    all_scores = []
    sources    = {}

    for label, data in [("Yahoo Finance", yf_data), ("NewsAPI", newsapi_data)]:
        if data is None:
            sources[label] = {"available": False}
            continue
        sources[label] = {"available": True, **data}
        all_scores.extend([h["score"] for h in data["headlines"]])

    avg = float(np.mean(all_scores)) if all_scores else 0.0

    # Collect all headlines sorted by absolute score (most opinionated first)
    all_headlines = []
    for data in [yf_data, newsapi_data]:
        if data:
            all_headlines.extend(data["headlines"])
    all_headlines.sort(key=lambda h: abs(h["score"]), reverse=True)

    return {
        "averageScore":   round(avg, 3),
        "sentimentLabel": "Bullish" if avg > 0.05 else "Bearish" if avg < -0.05 else "Neutral",
        "articleCount":   len(all_scores),
        "headlines":      all_headlines[:12],
        "positiveCount":  sum(1 for s in all_scores if s > 0.05),
        "negativeCount":  sum(1 for s in all_scores if s < -0.05),
        "neutralCount":   sum(1 for s in all_scores if -0.05 <= s <= 0.05),
        "sources":        sources,
    }


def backtest(ticker: str) -> dict | None:
    """
    Walk-forward backtest:
      - Train on first 65% of 3yr history
      - Test on remaining 35% (no data leakage)
      - Evaluate XGBoost, LSTM, and Ensemble accuracy separately
      - Simulate a simple strategy: buy when Bullish, hold cash when Bearish
    """
    t    = yf.Ticker(ticker)
    hist = t.history(period="3y")
    hist = hist[hist["Close"].notna()].copy()
    if len(hist) < 150:
        return None

    df = _compute_features(hist)
    df["forward_ret"] = df["Close"].pct_change(HORIZON).shift(-HORIZON)
    df["label"]       = (df["forward_ret"] > 0).astype(int)

    feat_cols = _feature_cols_for(df)
    df_clean  = df.dropna(subset=feat_cols + ["forward_ret"])

    split      = int(len(df_clean) * 0.65)
    train_df   = df_clean.iloc[:split]
    test_df    = df_clean.iloc[split:]

    if len(train_df) < 120 or len(test_df) < 30:
        return None

    # ── Train XGBoost on train split ──────────────────────────────────────────
    xgb = XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.75, min_child_weight=5,
        eval_metric="logloss", verbosity=0, random_state=42,
    )
    xgb.fit(train_df[feat_cols].values, train_df["label"].values)
    xgb_probs_test = xgb.predict_proba(test_df[feat_cols].values)[:, 1]

    # ── Train LSTM on train-split sequences, infer on test sequences ──────────
    feat_df   = df[LSTM_FEATURES].copy()
    means     = feat_df.iloc[:split + int(len(df) * 0.35)].mean()  # normalise on train only
    stds      = feat_df.iloc[:split + int(len(df) * 0.35)].std().replace(0, 1)
    feat_norm = ((feat_df - means) / stds).values.astype(np.float32)

    labels_arr = df["label"].values
    valid_arr  = df["forward_ret"].notna().values
    close_arr  = df["Close"].values

    # Build train sequences
    df_full_idx = df.index
    train_end_loc = df.index.get_loc(train_df.index[-1]) if hasattr(df.index, 'get_loc') else split

    X_tr, y_tr = [], []
    X_te, y_te = [], []
    te_close   = []  # closing prices for return simulation

    full_idx = list(range(len(df)))
    for i in full_idx:
        if i < LOOKBACK:
            continue
        seq = feat_norm[i - LOOKBACK : i]
        if np.any(np.isnan(seq)) or not valid_arr[i]:
            continue
        row_date = df.index[i]
        in_train = row_date <= train_df.index[-1]
        if in_train:
            X_tr.append(seq)
            y_tr.append(float(labels_arr[i]))
        else:
            X_te.append(seq)
            y_te.append(float(labels_arr[i]))
            te_close.append(float(close_arr[i]))

    lstm_probs_test = None
    if len(X_tr) >= 80 and len(X_te) >= 10:
        X_tr_t = torch.from_numpy(np.array(X_tr, dtype=np.float32))
        y_tr_t = torch.from_numpy(np.array(y_tr, dtype=np.float32))

        pos_ratio  = float(y_tr_t.mean())
        neg_ratio  = 1.0 - pos_ratio
        pos_weight = torch.tensor([neg_ratio / pos_ratio]) if pos_ratio > 0 else torch.tensor([1.0])

        loader  = DataLoader(TensorDataset(X_tr_t, y_tr_t), batch_size=32, shuffle=True)
        device  = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        model   = LSTMNet(n_features=len(LSTM_FEATURES)).to(device)
        opt     = torch.optim.Adam(model.parameters(), lr=5e-4, weight_decay=1e-4)
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight.to(device))

        model.train()
        best_loss, patience, no_improve = float("inf"), 8, 0
        for _ in range(50):
            ep_loss = 0.0
            for xb, yb in loader:
                xb, yb = xb.to(device), yb.to(device)
                opt.zero_grad()
                loss = loss_fn(model(xb), yb)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                ep_loss += loss.item()
            avg = ep_loss / len(loader)
            if avg < best_loss - 1e-4:
                best_loss, no_improve = avg, 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    break

        model.eval()
        X_te_t = torch.from_numpy(np.array(X_te, dtype=np.float32)).to(device)
        with torch.no_grad():
            lstm_probs_test = torch.sigmoid(model(X_te_t)).cpu().numpy()

    # ── Align arrays ──────────────────────────────────────────────────────────
    # test_df and LSTM test sequences may differ slightly in length due to
    # LOOKBACK warmup. Align to the shorter one.
    n = min(len(xgb_probs_test), len(y_te) if lstm_probs_test is not None else len(xgb_probs_test))
    xgb_p  = xgb_probs_test[:n]
    y_true  = np.array(y_te[:n]) if lstm_probs_test is not None else test_df["label"].values[:n]
    closes  = np.array(te_close[:n]) if te_close else test_df["Close"].values[:n]

    if lstm_probs_test is not None:
        lstm_p = lstm_probs_test[:n]
        ens_p  = XGB_WEIGHT * xgb_p + LSTM_WEIGHT * lstm_p
    else:
        ens_p  = xgb_p
        lstm_p = None

    def _accuracy(probs, truth):
        preds = (probs >= 0.5).astype(int)
        return float((preds == truth).mean() * 100)

    def _accuracy_when_confident(probs, truth, threshold=0.60):
        mask = (probs >= threshold) | (probs <= (1 - threshold))
        if mask.sum() < 5:
            return None, int(mask.sum())
        return float((( probs[mask] >= 0.5).astype(int) == truth[mask]).mean() * 100), int(mask.sum())

    # ── Simulated strategy: buy when ensemble says Bullish, else hold cash ────
    test_prices = test_df["Close"].values[:n]
    strategy_returns = []
    bah_returns      = []
    for i in range(0, len(test_prices) - HORIZON, HORIZON):
        entry  = test_prices[i]
        exit_  = test_prices[min(i + HORIZON, len(test_prices) - 1)]
        actual = (exit_ - entry) / entry * 100

        if ens_p[i] >= 0.5:                      # model says Bullish → buy
            strategy_returns.append(actual)
        else:                                      # model says Bearish → cash
            strategy_returns.append(0.0)
        bah_returns.append(actual)                 # buy-and-hold always holds

    conf_acc, conf_n = _accuracy_when_confident(ens_p, y_true)

    baseline_pct_up = float(y_true.mean() * 100)
    test_start = str(test_df.index[0].date()) if hasattr(test_df.index[0], 'date') else str(test_df.index[0])[:10]
    test_end   = str(test_df.index[-1].date()) if hasattr(test_df.index[-1], 'date') else str(test_df.index[-1])[:10]

    return {
        "ticker":     ticker,
        "testPeriod": {"start": test_start, "end": test_end, "predictions": n},
        "baseline":   {"pctUp": round(baseline_pct_up, 1)},
        "accuracy": {
            "xgboost":  round(_accuracy(xgb_p, y_true), 1),
            "lstm":     round(_accuracy(lstm_p, y_true), 1) if lstm_p is not None else None,
            "ensemble": round(_accuracy(ens_p,  y_true), 1),
        },
        "whenConfident": {
            "threshold":  60,
            "accuracy":   round(conf_acc, 1) if conf_acc is not None else None,
            "nPredictions": conf_n,
        },
        "simulatedStrategy": {
            "followModel":  round(sum(strategy_returns), 1),
            "buyAndHold":   round(sum(bah_returns), 1),
            "nTrades":      sum(1 for r in strategy_returns if r != 0),
            "winRate":      round(sum(1 for r in strategy_returns if r > 0) /
                                  max(1, sum(1 for r in strategy_returns if r != 0)) * 100, 1),
        },
    }


def blend_prediction(prediction: dict, sentiment: dict) -> dict:
    """3-way ensemble: XGBoost + LSTM + Sentiment news signal."""
    sent_score = sentiment["averageScore"]
    sent_prob  = (sent_score + 1) / 2   # map VADER [-1, 1] → probability [0, 1]

    breakdown = prediction["modelBreakdown"]
    xgb_p  = breakdown["xgboost"] / 100
    lstm_p = breakdown["lstm"] / 100 if breakdown["lstm"] is not None else None

    if lstm_p is not None:
        ensemble_prob = XGB_WEIGHT * xgb_p + LSTM_WEIGHT * lstm_p + SENT_WEIGHT * sent_prob
        models_used   = ["XGBoost", "LSTM", "Sentiment"]
    else:
        ensemble_prob = (1 - SENT_WEIGHT) * xgb_p + SENT_WEIGHT * sent_prob
        models_used   = ["XGBoost", "Sentiment"]

    direction = "Bullish" if ensemble_prob >= 0.5 else "Bearish"
    raw_conf  = ensemble_prob if ensemble_prob >= 0.5 else (1 - ensemble_prob)

    return {
        **prediction,
        "direction":          direction,
        "confidence":         round(raw_conf * 100, 1),
        "adjustedConfidence": round(raw_conf * 100, 1),
        "probUp":             round(ensemble_prob * 100, 1),
        "modelsUsed":         models_used,
        "modelBreakdown": {
            **breakdown,
            "sentiment": round(sent_prob * 100, 1),
            "ensemble":  round(ensemble_prob * 100, 1),
        },
        "sentiment": sentiment,
    }
