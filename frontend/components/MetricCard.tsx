interface Props {
  label: string;
  value: string;
  positive?: boolean | null;
  note?: string;
}

export default function MetricCard({ label, value, positive, note }: Props) {
  const valueColor =
    positive === true  ? "var(--green)" :
    positive === false ? "var(--red)"   : "var(--text)";

  return (
    <div className="flex items-center justify-between">
      <span className="text-xs" style={{ color: "var(--muted)" }}>{label}</span>
      <div className="flex items-center gap-2">
        {note && (
          <span className="text-xs" style={{ color: valueColor, opacity: 0.7 }}>{note}</span>
        )}
        <span className="text-sm font-semibold tabular-nums" style={{ color: valueColor }}>
          {value}
        </span>
      </div>
    </div>
  );
}
