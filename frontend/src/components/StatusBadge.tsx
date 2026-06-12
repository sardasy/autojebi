type Props = { value: string };

const PALETTE: Record<string, string> = {
  collected: "bg-slate-600 text-white",
  analyzed: "bg-cyan-700 text-white",
  form_filled: "bg-indigo-700 text-white",
  notified: "bg-emerald-600 text-white",
  digest_queued: "bg-amber-600 text-white",
  archived_low: "bg-slate-800 text-slate-400",
};

const LABEL: Record<string, string> = {
  collected: "수집",
  analyzed: "분석",
  form_filled: "양식",
  notified: "알림",
  digest_queued: "다이제스트",
  archived_low: "보류",
};

export function StatusBadge({ value }: Props) {
  const cls = PALETTE[value] || "bg-slate-700 text-slate-300";
  const label = LABEL[value] || value || "?";
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}
