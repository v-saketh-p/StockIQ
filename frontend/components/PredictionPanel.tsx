"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Brain, Newspaper, BarChart2, RefreshCw, FlaskConical } from "lucide-react";

interface Signal {
  feature: string;
  importance: number;
}

interface Headline {
  title: string;
  score: number;
  sentiment: "Positive" | "Negative" | "Neutral";
}

interface SourceData {
  available: boolean;
  averageScore?: number;
  label?: string;
  count?: number;
  positiveCount?: number;
  negativeCount?: number;
  neutralCount?: number;
}

interface SentimentData {
  averageScore: number;
  sentimentLabel: "Bullish" | "Bearish" | "Neutral";
  articleCount: number;
  headlines: Headline[];
  positiveCount: number;
  negativeCount: number;
  neutralCount: number;
  sources?: { [key: string]: SourceData };
}

interface ModelBreakdown {
  xgboost: number;
  lstm: number | null;
  lstmUncertainty: number | null;
  sentiment: number;
  ensemble: number;
}

interface PredictionData {
  direction: "Bullish" | "Bearish";
  confidence: number;
  adjustedConfidence: number;
  probUp: number;
  currentPrice: number;
  priceTargetLow: number;
  priceTargetHigh: number;
  topSignals: Signal[];
  modelsUsed: string[];
  modelBreakdown: ModelBreakdown;
  horizonDays: number;
  sentiment: SentimentData;
}

function ConfidenceRing({ value, direction }: { value: number; direction: "Bullish" | "Bearish" }) {
  const radius = 40;
  const circ   = 2 * Math.PI * radius;
  const pct    = value / 100;
  const color  = direction === "Bullish" ? "#22c55e" : "#ef4444";

  return (
    <div className="relative flex items-center justify-center" style={{ width: 110, height: 110 }}>
      <svg width="110" height="110" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="55" cy="55" r={radius} fill="none" stroke="var(--border)" strokeWidth="8" />
        <circle
          cx="55" cy="55" r={radius} fill="none"
          stroke={color} strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct)}
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-2xl font-black tabular-nums" style={{ color }}>{value.toFixed(0)}%</span>
        <span className="text-xs font-semibold" style={{ color: "var(--muted)" }}>confidence</span>
      </div>
    </div>
  );
}

function PriceRangeBar({
  low, current, high, direction,
}: {
  low: number; current: number; high: number; direction: "Bullish" | "Bearish";
}) {
  const range    = high - low;
  const curPct   = range > 0 ? ((current - low) / range) * 100 : 50;
  const bullColor = "#22c55e";
  const bearColor = "#ef4444";
  const color     = direction === "Bullish" ? bullColor : bearColor;

  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-2 rounded-full" style={{ background: "var(--border)" }}>
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${curPct}%`, background: color, opacity: 0.35 }} />
        <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-white"
          style={{ left: `calc(${curPct}% - 6px)`, background: color, boxShadow: `0 0 6px ${color}88` }} />
      </div>
      <div className="flex justify-between text-xs tabular-nums font-semibold">
        <span style={{ color: "#ef4444" }}>${low.toFixed(2)}</span>
        <span style={{ color: "var(--muted)" }}>now ${current.toFixed(2)}</span>
        <span style={{ color: "#22c55e" }}>${high.toFixed(2)}</span>
      </div>
    </div>
  );
}

function ModelBar({ label, value, color, isEnsemble, uncertainty }: {
  label: string; value: number | null; color: string; isEnsemble?: boolean; uncertainty?: number | null;
}) {
  if (value === null) return null;
  const bullish = value >= 50;

  const uncertaintyColor = uncertainty == null ? null
    : uncertainty < 5  ? "#22c55e"
    : uncertainty < 15 ? "#f59e0b"
    : "#ef4444";

  const uncertaintyLabel = uncertainty == null ? null
    : uncertainty < 5  ? "confident"
    : uncertainty < 15 ? "moderate"
    : "uncertain";

  return (
    <div className={`flex flex-col gap-1.5 ${isEnsemble ? "pt-2 border-t" : ""}`}
      style={isEnsemble ? { borderColor: "var(--border)" } : {}}>
      <div className="flex items-center gap-3">
        <span className={`text-xs w-20 flex-shrink-0 ${isEnsemble ? "font-bold" : ""}`}
          style={{ color: isEnsemble ? "var(--text)" : "var(--muted)" }}>
          {label}
        </span>
        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
          <div className="h-full rounded-full transition-all duration-700"
            style={{ width: `${value}%`, background: color }} />
        </div>
        <span className={`text-xs tabular-nums w-12 text-right ${isEnsemble ? "font-bold" : ""}`}
          style={{ color: bullish ? "#22c55e" : "#ef4444" }}>
          {value.toFixed(1)}% {bullish ? "↑" : "↓"}
        </span>
      </div>
      {uncertainty != null && (
        <div className="flex items-center gap-2 pl-23" style={{ paddingLeft: "5.75rem" }}>
          <span className="text-xs font-bold px-2 py-0.5 rounded-full tabular-nums"
            style={{ background: `${uncertaintyColor}22`, color: uncertaintyColor }}>
            ±{uncertainty.toFixed(1)}%
          </span>
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            model is {uncertaintyLabel} — based on 5 runs
          </span>
        </div>
      )}
    </div>
  );
}

function SentimentBar({ positive, negative, neutral, total }: {
  positive: number; negative: number; neutral: number; total: number;
}) {
  if (total === 0) return null;
  const posPct  = (positive / total) * 100;
  const negPct  = (negative / total) * 100;
  const neuPct  = (neutral  / total) * 100;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex h-2 rounded-full overflow-hidden gap-0.5">
        <div style={{ width: `${posPct}%`, background: "#22c55e" }} />
        <div style={{ width: `${neuPct}%`, background: "#94a3b8" }} />
        <div style={{ width: `${negPct}%`, background: "#ef4444" }} />
      </div>
      <div className="flex gap-3 text-xs" style={{ color: "var(--muted)" }}>
        <span><span className="font-bold" style={{ color: "#22c55e" }}>{positive}</span> bullish</span>
        <span><span className="font-bold" style={{ color: "#94a3b8" }}>{neutral}</span> neutral</span>
        <span><span className="font-bold" style={{ color: "#ef4444" }}>{negative}</span> bearish</span>
      </div>
    </div>
  );
}

// ── Backtest types ────────────────────────────────────────────────────────────

interface EquityPoint {
  date: string;
  model: number;
  buyAndHold: number;
}

interface BacktestData {
  ticker: string;
  testPeriod: { start: string; end: string; predictions: number };
  baseline: { pctUp: number };
  accuracy: { xgboost: number; lstm: number | null; ensemble: number };
  whenConfident: { threshold: number; accuracy: number | null; nPredictions: number };
  simulatedStrategy: { followModel: number; buyAndHold: number; nTrades: number; winRate: number };
  equityCurve: EquityPoint[];
}

function EquityCurveChart({ data }: { data: EquityPoint[] }) {
  if (!data || data.length < 2) return null;

  const VW = 400, VH = 140;
  const pad = { top: 10, right: 10, bottom: 22, left: 40 };
  const chartW = VW - pad.left - pad.right;
  const chartH = VH - pad.top - pad.bottom;

  const allVals = data.flatMap(d => [d.model, d.buyAndHold]);
  const minV = Math.min(...allVals) * 0.97;
  const maxV = Math.max(...allVals) * 1.02;

  const xi = (i: number) => pad.left + (i / (data.length - 1)) * chartW;
  const yi = (v: number) => pad.top + (1 - (v - minV) / (maxV - minV)) * chartH;

  const modelPath  = data.map((d, i) => `${i === 0 ? "M" : "L"}${xi(i).toFixed(1)},${yi(d.model).toFixed(1)}`).join(" ");
  const bahPath    = data.map((d, i) => `${i === 0 ? "M" : "L"}${xi(i).toFixed(1)},${yi(d.buyAndHold).toFixed(1)}`).join(" ");

  const modelFinal = data[data.length - 1].model;
  const bahFinal   = data[data.length - 1].buyAndHold;
  const modelWon   = modelFinal >= bahFinal;
  const modelColor = modelWon ? "#22c55e" : "#ef4444";

  // Year labels — one per year, skip crowding
  const yearLabels: { label: string; i: number }[] = [];
  let lastYear = "";
  data.forEach((d, i) => {
    const yr = d.date.slice(0, 4);
    if (yr !== lastYear) { yearLabels.push({ label: yr, i }); lastYear = yr; }
  });

  // Y-axis ticks
  const yTicks = [minV, (minV + maxV) / 2, maxV];

  return (
    <div className="flex flex-col gap-2">
      <svg viewBox={`0 0 ${VW} ${VH}`} style={{ width: "100%", height: "auto" }}>
        {/* Grid */}
        {yTicks.map(v => (
          <g key={v}>
            <line x1={pad.left} y1={yi(v)} x2={VW - pad.right} y2={yi(v)}
              stroke="var(--border)" strokeWidth="0.5" strokeDasharray="3,3" />
            <text x={pad.left - 4} y={yi(v)} textAnchor="end" dominantBaseline="middle"
              fontSize="8" fill="var(--muted)">${v.toFixed(0)}</text>
          </g>
        ))}

        {/* $100 baseline */}
        <line x1={pad.left} y1={yi(100)} x2={VW - pad.right} y2={yi(100)}
          stroke="#94a3b8" strokeWidth="0.5" opacity="0.4" />

        {/* Buy & hold */}
        <path d={bahPath} fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4,2" />

        {/* Model */}
        <path d={modelPath} fill="none" stroke={modelColor} strokeWidth="2" />

        {/* Year labels */}
        {yearLabels.map(({ label, i }) => i > 0 && (
          <text key={label} x={xi(i)} y={VH - 4} textAnchor="middle" fontSize="8" fill="var(--muted)">
            {label}
          </text>
        ))}
      </svg>

      {/* Legend */}
      <div className="flex gap-5 text-xs">
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0.5 rounded" style={{ background: modelColor }} />
          <span style={{ color: "var(--muted)" }}>
            Follow model →{" "}
            <span className="font-bold tabular-nums" style={{ color: modelColor }}>
              ${modelFinal.toFixed(0)}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-px rounded" style={{ background: "#94a3b8" }} />
          <span style={{ color: "var(--muted)" }}>
            Buy &amp; hold →{" "}
            <span className="font-bold tabular-nums" style={{ color: "#94a3b8" }}>
              ${bahFinal.toFixed(0)}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

function AccuracyBar({ label, value, baseline, color }: {
  label: string; value: number | null; baseline: number; color: string;
}) {
  if (value === null) return null;
  const beat = value >= baseline;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs">
        <span style={{ color: "var(--muted)" }}>{label}</span>
        <span className="font-bold tabular-nums" style={{ color: beat ? "#22c55e" : "#ef4444" }}>
          {value.toFixed(1)}% {beat ? "▲" : "▼"}
        </span>
      </div>
      <div className="relative h-2 rounded-full" style={{ background: "var(--border)" }}>
        {/* baseline marker */}
        <div className="absolute top-0 bottom-0 w-px" style={{ left: `${baseline}%`, background: "#94a3b8" }} />
        <div className="h-full rounded-full" style={{ width: `${Math.min(value, 100)}%`, background: color, opacity: 0.85 }} />
      </div>
    </div>
  );
}

function BacktestPanel({ ticker }: { ticker: string }) {
  const [data,    setData]    = useState<BacktestData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [ran,     setRan]     = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    setRan(true);
    try {
      const res = await fetch(`http://localhost:8000/api/stock/${ticker}/backtest`);
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Backtest failed"); }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  if (!ran) {
    return (
      <div className="rounded-xl p-5 flex flex-col items-center gap-3 text-center"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #10b981" }}>
        <FlaskConical size={22} style={{ color: "#10b981" }} />
        <div>
          <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>Backtest accuracy</p>
          <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
            Tests XGBoost + LSTM on the last 35% of history they never saw during training. Takes ~30s.
          </p>
        </div>
        <button onClick={run}
          className="px-4 py-2 rounded-lg text-xs font-bold"
          style={{ background: "#10b9811a", color: "#10b981", border: "1px solid #10b98133" }}>
          Run Backtest
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-xl p-6 flex flex-col items-center gap-3"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #10b981" }}>
        <div className="w-8 h-8 rounded-full border-2 animate-spin"
          style={{ borderColor: "#10b981", borderTopColor: "transparent" }} />
        <p className="text-xs" style={{ color: "var(--muted)" }}>Training models on 65% of history, testing on 35%…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl p-4 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <p className="text-xs" style={{ color: "#ef4444" }}>{error}</p>
        <button onClick={run} className="mt-2 text-xs underline" style={{ color: "var(--muted)" }}>Retry</button>
      </div>
    );
  }

  if (!data) return null;

  const { testPeriod, baseline, accuracy, whenConfident, simulatedStrategy } = data;
  const modelBeat = accuracy.ensemble >= baseline.pctUp;

  return (
    <div className="rounded-xl p-4 flex flex-col gap-4"
      style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #10b981" }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: "#10b9811a" }}>
            <FlaskConical size={13} style={{ color: "#10b981" }} />
          </div>
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
            Backtest · {testPeriod.start} → {testPeriod.end}
          </span>
        </div>
        <button onClick={run} className="text-xs" style={{ color: "var(--muted)" }}>
          <RefreshCw size={11} />
        </button>
      </div>

      {/* Baseline callout */}
      <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "var(--surface2)" }}>
        <span style={{ color: "var(--muted)" }}>Baseline (always say Bullish): </span>
        <span className="font-bold" style={{ color: "var(--text)" }}>{baseline.pctUp}%</span>
        <span style={{ color: "var(--muted)" }}> — {testPeriod.predictions} test predictions over {Math.round(testPeriod.predictions / 21)} months</span>
      </div>

      {/* Accuracy bars */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
          Directional accuracy (gray line = baseline)
        </p>
        <AccuracyBar label="XGBoost"  value={accuracy.xgboost}  baseline={baseline.pctUp} color="#f59e0b" />
        <AccuracyBar label="LSTM"     value={accuracy.lstm}     baseline={baseline.pctUp} color="#8b5cf6" />
        <AccuracyBar label="Ensemble" value={accuracy.ensemble} baseline={baseline.pctUp} color="#06b6d4" />
      </div>

      {/* When confident */}
      {whenConfident.accuracy !== null && (
        <div className="rounded-lg px-3 py-2.5 flex justify-between items-center"
          style={{ background: whenConfident.accuracy >= baseline.pctUp ? "#22c55e0d" : "#ef44440d",
                   border: `1px solid ${whenConfident.accuracy >= baseline.pctUp ? "#22c55e22" : "#ef444422"}` }}>
          <div>
            <p className="text-xs font-semibold" style={{ color: "var(--text)" }}>
              When ensemble is &gt;{whenConfident.threshold}% confident
            </p>
            <p className="text-xs" style={{ color: "var(--muted)" }}>{whenConfident.nPredictions} of {testPeriod.predictions} predictions</p>
          </div>
          <span className="text-lg font-black tabular-nums"
            style={{ color: whenConfident.accuracy >= baseline.pctUp ? "#22c55e" : "#ef4444" }}>
            {whenConfident.accuracy.toFixed(1)}%
          </span>
        </div>
      )}

      {/* Equity curve */}
      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
          $100 invested at start of test period
        </p>
        <EquityCurveChart data={data.equityCurve} />
      </div>

      {/* Simulated strategy stats */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: "Follow model", value: simulatedStrategy.followModel, sub: `${simulatedStrategy.nTrades} trades · ${simulatedStrategy.winRate}% win rate` },
          { label: "Buy & Hold",   value: simulatedStrategy.buyAndHold,  sub: "always invested" },
        ].map(({ label, value, sub }) => (
          <div key={label} className="rounded-lg p-3 flex flex-col gap-0.5"
            style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            <span className="text-xs" style={{ color: "var(--muted)" }}>{label}</span>
            <span className="text-xl font-black tabular-nums"
              style={{ color: value >= 100 ? "#22c55e" : "#ef4444" }}>
              ${value.toFixed(0)}
            </span>
            <span className="text-xs" style={{ color: "var(--muted)" }}>{sub}</span>
          </div>
        ))}
      </div>

      <p className="text-xs" style={{ color: "var(--muted)" }}>
        {modelBeat
          ? "Ensemble beat the naive baseline on this ticker's test period."
          : "Ensemble underperformed the naive baseline — common in strong bull runs where always-up wins."}
      </p>
    </div>
  );
}

export default function PredictionPanel({ ticker }: { ticker: string }) {
  const [data,    setData]    = useState<PredictionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  async function fetchPrediction() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/stock/${ticker}/prediction`);
      if (!res.ok) {
        const j = await res.json();
        throw new Error(j.detail || "Prediction failed");
      }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchPrediction(); }, [ticker]);

  const bullColor = "#22c55e";
  const bearColor = "#ef4444";

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <div className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
        <div className="text-sm" style={{ color: "var(--muted)" }}>
          Training ML model on full available history…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="text-sm" style={{ color: "var(--muted)" }}>{error}</p>
        <button onClick={fetchPrediction}
          className="text-xs px-4 py-2 rounded-lg font-semibold"
          style={{ background: "var(--surface2)", color: "var(--text)" }}>
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const { direction, adjustedConfidence, probUp, currentPrice,
          priceTargetLow, priceTargetHigh, topSignals,
          modelsUsed, modelBreakdown, horizonDays, sentiment } = data;

  const dirColor = direction === "Bullish" ? bullColor : bearColor;
  const DirIcon  = direction === "Bullish" ? TrendingUp : TrendingDown;

  return (
    <div className="flex flex-col gap-4">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{ background: `${dirColor}1a` }}>
            <Brain size={13} style={{ color: dirColor }} />
          </div>
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
            ML Forecast · {horizonDays}-day
          </span>
        </div>
        <button onClick={fetchPrediction}
          className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg"
          style={{ background: "var(--surface2)", color: "var(--muted2)" }}>
          <RefreshCw size={11} />
          Refresh
        </button>
      </div>

      {/* ── Verdict card ── */}
      <div className="rounded-xl p-5 flex flex-col gap-4"
        style={{ background: "var(--surface)", border: `1px solid var(--border)`, borderTop: `2px solid ${dirColor}` }}>

        <div className="flex items-center justify-between">
          {/* Direction */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <DirIcon size={22} style={{ color: dirColor }} />
              <span className="text-3xl font-black" style={{ color: dirColor }}>{direction}</span>
            </div>
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              {probUp.toFixed(0)}% probability of being higher in {horizonDays} days
            </span>
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              {modelsUsed.join(" + ")} ensemble
            </span>
          </div>

          {/* Confidence ring */}
          <ConfidenceRing value={adjustedConfidence} direction={direction} />
        </div>

        {/* Price target bar */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
            30-day price range
          </span>
          <PriceRangeBar
            low={priceTargetLow}
            current={currentPrice}
            high={priceTargetHigh}
            direction={direction}
          />
        </div>
      </div>

      {/* ── Model breakdown ── */}
      <div className="rounded-xl p-4 flex flex-col gap-3"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #06b6d4" }}>
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: "#06b6d41a" }}>
            <Brain size={13} style={{ color: "#06b6d4" }} />
          </div>
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
            Model breakdown — % chance stock is higher
          </span>
        </div>
        <div className="flex flex-col gap-2.5">
          <ModelBar label="XGBoost"   value={modelBreakdown.xgboost}   color="#f59e0b" />
          <ModelBar label="LSTM"      value={modelBreakdown.lstm}       color="#8b5cf6" uncertainty={modelBreakdown.lstmUncertainty} />
          <ModelBar label="Sentiment" value={modelBreakdown.sentiment}  color="#22c55e" />
          <ModelBar label="Ensemble"  value={modelBreakdown.ensemble}   color="#06b6d4" isEnsemble />
        </div>
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          XGBoost reads today&apos;s snapshot signals. LSTM reads the last 60 days as a sequence.
          Sentiment converts live news tone into a probability. Ensemble = 45% XGBoost + 35% LSTM + 20% Sentiment.
        </p>
      </div>

      {/* ── Top signals ── */}
      <div className="rounded-xl p-4 flex flex-col gap-3"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #8b5cf6" }}>
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: "#8b5cf61a" }}>
            <BarChart2 size={13} style={{ color: "#8b5cf6" }} />
          </div>
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
            Key signals driving forecast
          </span>
        </div>
        <div className="flex flex-col gap-2">
          {topSignals.map((sig) => (
            <div key={sig.feature} className="flex items-center gap-2">
              <span className="text-xs w-36 flex-shrink-0" style={{ color: "var(--muted)" }}>{sig.feature}</span>
              <div className="flex-1 h-1.5 rounded-full" style={{ background: "var(--border)" }}>
                <div className="h-full rounded-full" style={{ width: `${Math.min(sig.importance * 4, 100)}%`, background: "#8b5cf6" }} />
              </div>
              <span className="text-xs tabular-nums w-10 text-right" style={{ color: "var(--muted2)" }}>
                {sig.importance.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── News sentiment ── */}
      <div className="rounded-xl p-4 flex flex-col gap-3"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #f59e0b" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: "#f59e0b1a" }}>
              <Newspaper size={13} style={{ color: "#f59e0b" }} />
            </div>
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
              Sentiment · {sentiment.articleCount} articles
            </span>
          </div>
          <span className="text-xs font-bold px-2 py-0.5 rounded-full"
            style={{
              background: sentiment.sentimentLabel === "Bullish" ? "#22c55e1a"
                        : sentiment.sentimentLabel === "Bearish" ? "#ef44441a" : "#94a3b81a",
              color: sentiment.sentimentLabel === "Bullish" ? "#22c55e"
                   : sentiment.sentimentLabel === "Bearish" ? "#ef4444" : "#94a3b8",
            }}>
            {sentiment.sentimentLabel}
          </span>
        </div>

        {/* Per-source breakdown */}
        {sentiment.sources && (
          <div className="flex flex-col gap-1.5">
            {Object.entries(sentiment.sources).map(([name, src]) => {
              const sourceIcons: Record<string, string> = {
                "Yahoo Finance": "📰",
                "NewsAPI": "🌐",
              };
              if (!src.available) {
                return (
                  <div key={name} className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                    <span>{sourceIcons[name] ?? "•"}</span>
                    <span>{name}</span>
                    <span className="ml-auto text-xs px-1.5 py-0.5 rounded"
                      style={{ background: "var(--surface2)", color: "var(--muted)" }}>
                      No API key
                    </span>
                  </div>
                );
              }
              const lbl = src.label ?? "Neutral";
              return (
                <div key={name} className="flex items-center gap-2 text-xs">
                  <span>{sourceIcons[name] ?? "•"}</span>
                  <span style={{ color: "var(--muted)" }}>{name}</span>
                  <span style={{ color: "var(--muted)" }}>·</span>
                  <span style={{ color: "var(--muted)" }}>{src.count} articles</span>
                  <span className="ml-auto font-semibold"
                    style={{ color: lbl === "Bullish" ? "#22c55e" : lbl === "Bearish" ? "#ef4444" : "#94a3b8" }}>
                    {lbl}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        <SentimentBar
          positive={sentiment.positiveCount}
          negative={sentiment.negativeCount}
          neutral={sentiment.neutralCount}
          total={sentiment.articleCount}
        />

        <div className="flex flex-col gap-1.5 mt-1">
          {sentiment.headlines.map((h, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                style={{
                  background: h.sentiment === "Positive" ? "#22c55e"
                            : h.sentiment === "Negative" ? "#ef4444" : "#94a3b8",
                }} />
              <span className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{h.title}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Backtest ── */}
      <BacktestPanel ticker={ticker} />

      <p className="text-xs text-center pb-2" style={{ color: "var(--muted)" }}>
        For informational purposes only. Not financial advice.
      </p>
    </div>
  );
}
