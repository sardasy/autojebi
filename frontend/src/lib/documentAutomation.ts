import type { DocumentAutomationResult, NoticeRecord } from "./api";

export type BidWorkflowStepState = "done" | "current" | "pending" | "blocked";

export type BidWorkflowStep = {
  id: "review" | "documents" | "spec" | "compliance" | "proposal";
  label: string;
  state: BidWorkflowStepState;
  detail: string;
};

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
  if (notice.status === "collected") return "공고 분석 필요";
  if (!notice.graded_at) return "그레이딩 필요";

  const docs = readDocumentAutomation(notice);
  if (!docs) return "서류 분석 필요";

  const missingCount = requiredMissingCount(docs);
  if (missingCount > 0) return `필수 서류 준비 필요 (${missingCount}건)`;

  if ((notice.spec_item_count || 0) === 0) return "규격 추출 필요";

  if (!hasTechnicalComplianceExport(docs)) return "규격대응표 작성 필요";
  if (!hasProposalDraftOrExport(docs)) return "제안서 초안 생성 필요";

  if ((notice.unresolved_error_count || 0) > 0 || docs.errors.length > 0) {
    return "오류 확인 필요";
  }
  if (docs.ready_for_submission) return "최종 검토 가능";
  if (notice.status === "form_filled") return "제출 전 검증 필요";
  const label: Record<string, string> = {
    notified: "알림 완료",
    digest_queued: "다이제스트 대기",
    archived_low: "보류",
  };
  return label[notice.status] || "확인 필요";
}

export function bidWorkflowSteps(notice: NoticeRecord): BidWorkflowStep[] {
  const docs = readDocumentAutomation(notice);
  const graded = Boolean(notice.graded_at);
  const reviewed = notice.status !== "collected" && graded;
  const missingCount = docs ? requiredMissingCount(docs) : 0;
  const documentsDone = Boolean(docs && missingCount === 0);
  const specDone = (notice.spec_item_count || 0) > 0;
  const complianceDone = Boolean(docs && hasTechnicalComplianceExport(docs));
  const proposalDone = Boolean(docs && hasProposalDraftOrExport(docs));

  return [
    {
      id: "review",
      label: "공고 검토",
      state: reviewed ? "done" : "current",
      detail: reviewed ? "분석/그레이딩 완료" : notice.status === "collected" ? "공고 분석 필요" : "그레이딩 필요",
    },
    {
      id: "documents",
      label: "서류 준비",
      state: !reviewed ? "pending" : documentsDone ? "done" : "current",
      detail: !docs
        ? "서류 분석 필요"
        : missingCount > 0
          ? `필수 서류 ${missingCount}건 준비 필요`
          : "필수 서류 준비 완료",
    },
    {
      id: "spec",
      label: "규격 항목",
      state: !documentsDone ? "pending" : specDone ? "done" : "current",
      detail: specDone ? `${notice.spec_item_count}개 항목` : "규격 추출 필요",
    },
    {
      id: "compliance",
      label: "규격대응표",
      state: !specDone ? "pending" : complianceDone ? "done" : "current",
      detail: complianceDone ? "export 생성됨" : "Excel/HWP 작성 필요",
    },
    {
      id: "proposal",
      label: "제안서 초안",
      state: !complianceDone ? "pending" : proposalDone ? "done" : "current",
      detail: proposalDone ? "초안/파일 생성됨" : "제안서 초안 생성 필요",
    },
  ];
}

function requiredMissingCount(docs: DocumentAutomationResult): number {
  if (docs.missing_required.length > 0) return docs.missing_required.length;
  return docs.checklist.filter(
    (item) => item.required && !["ready", "generated", "not_applicable"].includes(item.status),
  ).length;
}

function hasTechnicalComplianceExport(docs: DocumentAutomationResult): boolean {
  return Boolean(
    docs.exports?.some(
      (item) =>
        (item.kind === "excel" || item.kind === "hwp") &&
        item.draft_id === "technical_compliance",
    ),
  );
}

function hasProposalDraftOrExport(docs: DocumentAutomationResult): boolean {
  return Boolean(
    docs.drafts?.proposal ||
      docs.exports?.some((item) => item.kind === "proposal_hwp" && item.draft_id === "proposal"),
  );
}
