import type { Healthz, HwpAgentHealthResponse, HwpTemplateRecord } from "@/lib/api";

type Props = {
  health: Healthz | null;
  healthError: string | null;
  hwpHealth: HwpAgentHealthResponse | null;
  hwpHealthError: string | null;
  hwpTemplates: HwpTemplateRecord[];
};

type ReadinessKind = "ok" | "warning" | "error";

export function DemoReadinessPanel({
  health,
  healthError,
  hwpHealth,
  hwpHealthError,
  hwpTemplates,
}: Props) {
  const checks = [
    {
      label: "API 서버",
      kind: health?.ok ? "ok" : "error",
      detail: health?.ok ? "연결됨" : healthError || "연결 실패",
    },
    {
      label: "DB 연결",
      kind: health?.checks?.db === "ok" ? "ok" : "error",
      detail: health?.checks?.db || "확인 불가",
    },
    {
      label: "G2B API 키 설정",
      kind: health?.checks?.DATA_GO_KR_API_KEY === "ok" ? "ok" : "warning",
      detail: health?.checks?.DATA_GO_KR_API_KEY || "키 상태 확인 필요",
    },
    {
      label: "Qdrant 주소 설정",
      kind: health?.checks?.QDRANT_URL === "ok" ? "ok" : "warning",
      detail: health?.checks?.QDRANT_URL || "인제스트/검색 상태 확인 필요",
    },
    {
      label: "HWP Worker",
      kind: hwpHealth?.ok ? "ok" : "warning",
      detail: hwpHealth?.ok
        ? `연결됨: ${hwpHealth.base_url}`
        : hwpHealth?.detail || hwpHealthError || "미연결 또는 상태 확인 실패",
    },
    {
      label: "HWP 템플릿/매핑 등록",
      kind: hwpTemplates.length >= 2 ? "ok" : hwpTemplates.length > 0 ? "warning" : "error",
      detail:
        hwpTemplates.length > 0
          ? `${hwpTemplates.length}개 템플릿 · ${hwpTemplates.reduce(
              (sum, item) => sum + item.mappings.length,
              0,
            )}개 매핑`
          : "템플릿 없음: python -m api.hwp_fields seed 필요",
    },
  ] satisfies Array<{ label: string; kind: ReadinessKind; detail: string }>;

  const blockers = checks.filter((item) => item.kind === "error").length;
  const warnings = checks.filter((item) => item.kind === "warning").length;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">연결 상태</h2>
        </div>
        <div
          role="status"
          className={`rounded border px-3 py-2 text-xs ${
            blockers > 0
              ? "border-red-800 bg-red-50/30 text-red-800"
              : warnings > 0
                ? "border-amber-800 bg-amber-50/20 text-amber-900"
                : "border-emerald-800 bg-emerald-50/20 text-emerald-800"
          }`}
        >
          {blockers > 0
            ? `차단 ${blockers}건 · 경고 ${warnings}건`
            : warnings > 0
              ? `경고 ${warnings}건 · 설정 확인 필요`
              : "기본 설정·접속 확인 · 실작업 검증 별도"}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {checks.map((item) => (
          <ReadinessCard key={item.label} item={item} />
        ))}
      </div>
    </section>
  );
}

function ReadinessCard({
  item,
}: {
  item: { label: string; kind: ReadinessKind; detail: string };
}) {
  const badge =
    item.kind === "ok"
      ? "border-emerald-700 bg-emerald-50/30 text-emerald-800"
      : item.kind === "warning"
        ? "border-amber-700 bg-amber-50/20 text-amber-900"
        : "border-red-800 bg-red-50/30 text-red-800";
  const label = item.kind === "ok" ? "OK" : item.kind === "warning" ? "확인" : "필수";
  return (
    <div className="rounded border border-slate-200 bg-white/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-900">{item.label}</div>
        <span className={`rounded border px-2 py-0.5 text-xs ${badge}`}>{label}</span>
      </div>
      <div className="mt-2 break-words text-xs text-slate-600">{item.detail}</div>
    </div>
  );
}
