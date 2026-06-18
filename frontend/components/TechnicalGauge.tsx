interface Props {
  label: string;
  value: number | null;
  min: number;
  max: number;
  low: number;
  high: number;
}

export default function TechnicalGauge({ label, value, min, max, low, high }: Props) {
  const pct = value !== null ? ((value - min) / (max - min)) * 100 : 0;
  const color =
    value === null       ? "var(--muted)" :
    value > high         ? "var(--red)"   :
    value < low          ? "var(--green)" : "var(--green)";

  const zone =
    value === null ? "" :
    value > high   ? "Overbought" :
    value < low    ? "Oversold"   : "Neutral";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs" style={{ color: "var(--muted)" }}>{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color, opacity: 0.7 }}>{zone}</span>
          <span className="text-sm font-semibold tabular-nums" style={{ color }}>
            {value !== null ? value.toFixed(2) : "N/A"}
          </span>
        </div>
      </div>
      <div className="relative h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface2)" }}>
        {/* zones */}
        <div
          className="absolute top-0 h-full rounded-full opacity-20"
          style={{ left: "0%", width: `${(low / max) * 100}%`, background: "var(--green)" }}
        />
        <div
          className="absolute top-0 h-full rounded-full opacity-20"
          style={{ left: `${(high / max) * 100}%`, width: `${((max - high) / max) * 100}%`, background: "var(--red)" }}
        />
        {/* indicator */}
        {value !== null && (
          <div
            className="absolute top-0 h-full w-1 rounded-full"
            style={{ left: `${pct}%`, background: color, transform: "translateX(-50%)" }}
          />
        )}
      </div>
      <div className="flex justify-between text-xs" style={{ color: "var(--muted)", opacity: 0.5 }}>
        <span>{min}</span>
        <span>{low} / {high}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
