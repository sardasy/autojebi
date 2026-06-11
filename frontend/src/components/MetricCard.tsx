type Props = {
  label: string;
  value: number | null;
  hint?: string;
};

/**
 * 3축 메트릭 카드 (사양/자격/예가/종합). value는 0~1 범위.
 * ScoreBadge 색상 룰과 일관성 있게 컬러링.
 */
export function MetricCard({ label, value, hint }: Props) {
  let color = "text-slate-400";
  if (value !== null && value !== undefined) {
    if (value >= 0.8) color = "text-emerald-400";
    else if (value >= 0.6) color = "text-amber-300";
    else if (value >= 0.4) color = "text-orange-400";
    else if (value > 0) color = "text-red-400";
    else color = "text-slate-500";
  }

  const display = value === null || value === undefined ? "—" : value.toFixed(2);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{display}</div>
      {hint ? <div className="text-xs text-slate-500 mt-1">{hint}</div> : null}
    </div>
  );
}
