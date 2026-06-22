type Props = {
  value: string | number | null;
  label?: string;
  mode?: "0to1" | "0to100";
};

export function ScoreBadge({ value, label, mode = "0to1" }: Props) {
  if (value === null || value === undefined) {
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-xs bg-slate-800 text-slate-500">
        {label ? `${label} —` : "—"}
      </span>
    );
  }
  const raw = typeof value === "string" ? parseFloat(value) : value;
  const n = mode === "0to100" ? raw / 100 : raw;

  const cls =
    n >= 0.8
      ? "bg-emerald-600 text-white"
      : n >= 0.6
        ? "bg-amber-500 text-slate-900"
        : n >= 0.4
          ? "bg-orange-500 text-white"
          : n > 0
            ? "bg-red-700 text-white"
            : "bg-slate-700 text-slate-400";

  const display = mode === "0to100" ? raw.toFixed(0) : n.toFixed(2);
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {label ? `${label} ` : ""}
      {display}
    </span>
  );
}
