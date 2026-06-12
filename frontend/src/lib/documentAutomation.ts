import type { DocumentAutomationResult, NoticeRecord } from "./api";

export function readDocumentAutomation(
  notice: NoticeRecord,
): DocumentAutomationResult | null {
  const raw = notice.analysis?.document_automation;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const value = raw as Partial<DocumentAutomationResult>;
  if (!Array.isArray(value.checklist)) return null;
  const result: DocumentAutomationResult = {
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
  if (Array.isArray(value.uploads)) result.uploads = value.uploads;
  if (Array.isArray(value.exports)) result.exports = value.exports;
  return result;
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
  const uploadCount = docs.uploads?.length || 0;
  const exportKinds = new Set((docs.exports || []).map((item) => item.kind));
  const baseText = `서류: ${ready}/${total} 준비 · 누락 ${missing} · 초안 ${draftCount}`;
  if (uploadCount === 0 && exportKinds.size === 0) return baseText;
  const exportText =
    exportKinds.size > 0 ? Array.from(exportKinds).join(", ").toUpperCase() : "없음";
  return `${baseText} · 업로드 ${uploadCount} · 내보내기 ${exportText}`;
}

export function nextNoticeAction(notice: NoticeRecord): string {
  if (notice.status === "collected") return "분석 필요";
  if (notice.status === "analyzed") {
    return notice.graded_at ? "서류 분석 필요" : "Grade/서류 분석 필요";
  }
  if (notice.status === "form_filled") return "제출 전 검증 필요";
  const label: Record<string, string> = {
    notified: "알림 완료",
    digest_queued: "다이제스트 대기",
    archived_low: "보류",
  };
  return label[notice.status] || "확인 필요";
}
