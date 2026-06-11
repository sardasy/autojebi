import type { DocumentAutomationResult, NoticeRecord } from "./api";

export function readDocumentAutomation(
  notice: NoticeRecord,
): DocumentAutomationResult | null {
  const raw = notice.analysis?.document_automation;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const value = raw as Partial<DocumentAutomationResult>;
  if (!Array.isArray(value.checklist)) return null;
  return {
    checklist: value.checklist,
    drafts: value.drafts || {},
    risks: Array.isArray(value.risks) ? value.risks : [],
    generated_at: value.generated_at || "",
    source: value.source || "unknown",
    ready_for_submission: Boolean(value.ready_for_submission),
    missing_required: Array.isArray(value.missing_required)
      ? value.missing_required
      : [],
    errors: Array.isArray(value.errors) ? value.errors : [],
  };
}

export function documentSummaryText(docs: DocumentAutomationResult): string {
  const total = docs.checklist.filter((item) => item.required).length;
  const ready = docs.checklist.filter(
    (item) => item.required && ["ready", "generated"].includes(item.status),
  ).length;
  const missing =
    docs.missing_required && docs.missing_required.length > 0
      ? docs.missing_required.length
      : Math.max(total - ready, 0);
  const draftCount = Object.keys(docs.drafts || {}).length;
  return `서류: ${ready}/${total} 준비 · 누락 ${missing} · 초안 ${draftCount}`;
}
