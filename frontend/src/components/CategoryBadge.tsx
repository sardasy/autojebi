type Props = { value: string };

/**
 * autojebi Category 색상 매핑.
 *  - HIL/SW → blue (Sangjun)
 *  - IGBT/SCR/수동소자/ABB장비 → orange (이용문)
 *  - 혼합 → purple
 *  - 비관련 → slate-700
 */
const PALETTE: Record<string, string> = {
  HIL: "bg-sky-700 text-white",
  SW: "bg-sky-700 text-white",
  IGBT: "bg-orange-600 text-white",
  SCR: "bg-orange-600 text-white",
  수동소자: "bg-orange-700 text-white",
  ABB장비: "bg-orange-500 text-white",
  혼합: "bg-purple-700 text-white",
  비관련: "bg-slate-700 text-slate-300",
};

export function CategoryBadge({ value }: Props) {
  const cls = PALETTE[value] || "bg-slate-700 text-slate-300";
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {value || "?"}
    </span>
  );
}
