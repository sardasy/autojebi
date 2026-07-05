import type { DocumentItemType } from "@/lib/api";

// 서류 출처 라벨 — 실무자가 "공고 필수"와 "회사 보조 후보"를 혼동하지 않게 한다.
export type DocOrigin =
  | { kind: "notice"; checked: boolean }
  | { kind: "checklist"; source: string; type: DocumentItemType };

function resolve(origin: DocOrigin): { text: string; cls: string } {
  if (origin.kind === "notice") {
    return origin.checked
      ? { text: "공고 원문 확인", cls: "border-emerald-700 bg-emerald-950/40 text-emerald-200" }
      : { text: "첨부 LLM 추출", cls: "border-sky-700 bg-sky-950/30 text-sky-200" };
  }
  const s = origin.source || "";
  if (s.includes("manual")) {
    return { text: "수동 추가", cls: "border-violet-700 bg-violet-950/30 text-violet-200" };
  }
  if (s.includes("llm")) {
    return { text: "첨부 LLM 추출", cls: "border-sky-700 bg-sky-950/30 text-sky-200" };
  }
  if (origin.type === "company_common") {
    return { text: "회사 공통 후보", cls: "border-slate-600 bg-slate-900 text-slate-300" };
  }
  return { text: "규칙 기반 추정", cls: "border-slate-700 bg-slate-900 text-slate-400" };
}

export function DocSourceBadge({ origin }: { origin: DocOrigin }) {
  const { text, cls } = resolve(origin);
  return (
    <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[11px] ${cls}`}>{text}</span>
  );
}
