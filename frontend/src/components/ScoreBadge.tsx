type Props = {
  value: string | number | null;
  label?: string;
  mode?: "0to1" | "0to100";
};

/**
 * 점수 색상 코딩 배지.
 *  - `mode="0to1"` (기본): score_total/score_spec/score_qual/score_price 용.
 *  - `mode="0to100"`: fit_score 용. 내부적으로 /100 후 동일 임계치 적용.
 */
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

  let cls = "bg-slate-700 text-slate-200";
  if (n >= 0.8) cls = "bg-emerald-600 text-white";
  else if (n >= 0.6) cls = "bg-amber-500 text-slate-900";
  else if (n >= 0.4) cls = "bg-orange-500 text-white";
  else if (n > 0) cls = "bg-red-700 text-white";
  else cls = "bg-slate-700 text-slate-400";

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
