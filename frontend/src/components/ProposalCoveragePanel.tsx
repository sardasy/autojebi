import type { ProposalCoverageResponse } from "@/lib/api";

const STATUS_LABEL = {
  ready: "준비됨",
  partial: "부분",
  missing: "근거 없음",
};

export function ProposalCoveragePanel({
  coverage,
  error,
}: {
  coverage: ProposalCoverageResponse | null;
  error?: string | null;
}) {
  if (error) {
    return (
      <div className="rounded border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-100">
        제안서 준비도를 불러오지 못했습니다: {error}
      </div>
    );
  }

  if (!coverage || coverage.items.length === 0) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500">
        제안서 요구사항 분석 전
      </div>
    );
  }

  const missing = coverage.items.filter((item) => item.status === "missing").length;

  return (
    <div className="space-y-3 rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase text-slate-400">
            Proposal readiness
          </div>
          <div className="mt-1 text-2xl font-semibold text-slate-100">
            {coverage.readiness_score}%
          </div>
        </div>
        <div className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-300">
          근거 없음 {missing}건
        </div>
      </div>

      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead className="bg-slate-950/70 text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2 text-left font-medium">요구사항</th>
              <th className="px-3 py-2 text-left font-medium">유형</th>
              <th className="px-3 py-2 text-left font-medium">근거</th>
              <th className="px-3 py-2 text-left font-medium">상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {coverage.items.map((item) => (
              <tr key={item.requirement_id}>
                <td className="max-w-xl px-3 py-2 text-slate-200">
                  <span className="line-clamp-2">{item.requirement_text}</span>
                </td>
                <td className="px-3 py-2 text-slate-400">{item.requirement_type}</td>
                <td className="px-3 py-2 text-slate-400">{item.evidence_count}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded px-2 py-1 text-xs ${
                      item.status === "ready"
                        ? "bg-emerald-500/10 text-emerald-200"
                        : item.status === "partial"
                          ? "bg-amber-500/10 text-amber-200"
                          : "bg-red-500/10 text-red-200"
                    }`}
                  >
                    {STATUS_LABEL[item.status]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
