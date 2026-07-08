import numpy as np
import pandas as pd


def compute_adx(high, low, close, period=14):
    """
    Average Directional Index (Wilder smoothing via EWM).
    Returns: (adx, plus_di, minus_di)
    """
    up_move   = high.diff()
    down_move = low.diff().mul(-1)

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    alpha = 1 / period
    atr_s      = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_s  = pd.Series(plus_dm,  index=high.index).ewm(alpha=alpha, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=high.index).ewm(alpha=alpha, adjust=False).mean()

    plus_di  = 100 * plus_dm_s  / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm_s / atr_s.replace(0, np.nan)

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()

    return adx, plus_di, minus_di


def compute_rsi(close, period=14):
    """Relative Strength Index using Wilder's EWM."""
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = delta.clip(upper=0).abs()

    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_bollinger_bands(close, period=20, std_dev=2.0):
    """Returns (upper, mid, lower, bb_pct_b) where bb_pct_b is 0–1 position within bands."""
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    band_width = (upper - lower).replace(0, np.nan)
    pct_b = (close - lower) / band_width  # 0 = at lower, 1 = at upper
    return upper, mid, lower, pct_b


def compute_momentum_12_1(close):
    """
    Jegadeesh-Titman 12-1 momentum factor.
    Returns 12-month return skipping the most recent month to avoid short-term reversal.
    252 trading days ≈ 12 months, 21 ≈ 1 month.
    """
    return close.shift(21) / close.shift(252) - 1


def compute_atr(high, low, close, period=14):
    """Average True Range for volatility-based stop sizing."""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_volume_ratio(volume, period=20):
    """Current volume / N-day average volume."""
    avg = volume.rolling(period).mean()
    return volume / avg.replace(0, np.nan)
