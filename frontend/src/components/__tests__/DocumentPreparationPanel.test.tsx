import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../Toast";
import type {
  DocumentAutomationResult,
  DocumentChecklistItem,
  NoticeRecord,
} from "@/lib/api";

vi.mock("@/lib/actions", () => ({
  actionAnalyzeDocuments: vi.fn(),
  actionUpdateDocumentChecklistItem: vi.fn(),
  actionValidateDocuments: vi.fn(),
}));

async function loadPanel() {
  const mod = await import("../DocumentPreparationPanel");
  return mod.DocumentPreparationPanel;
}

function mkItem(
  partial: Partial<DocumentChecklistItem> & { id: string },
): DocumentChecklistItem {
  return {
    name: partial.name ?? partial.id,
    type: partial.type ?? "other",
    required: partial.required ?? true,
    status: partial.status ?? "needed",
    owner: partial.owner ?? null,
    reason: partial.reason ?? null,
    source: partial.source ?? "rule",
    due_hint: partial.due_hint ?? null,
    note: partial.note ?? null,
    ...partial,
  };
}

function mkNotice(
  overrides: Partial<NoticeRecord> & {
    documentAutomation?: DocumentAutomationResult | null;
  } = {},
): NoticeRecord {
  const { documentAutomation, ...rest } = overrides;
  const analysis: Record<string, unknown> =
    documentAutomation !== undefined
      ? { document_automation: documentAutomation }
      : {};
  return {
    notice_no: "DOC-1",
    title: "ABB 변압기 구매",
    source: "G2B",
    raw: null,
    category: "ABB장비",
    fit_score: 80,
    assignee: "이용문",
    analysis,
    status: "analyzed",
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    bid_no: null,
    bid_seq: null,
    bid_type: null,
    org_code: null,
    org_name: null,
    base_price: null,
    open_date: null,
    close_date: null,
    collected_at: null,
    score_spec: null,
    score_qual: null,
    score_price: null,
    score_total: null,
    grade_reason: null,
    risk_note: null,
    top_sku: null,
    top_sku_name: null,
    sku_match_score: null,
    graded_at: null,
    ...rest,
  };
}

function renderPanel(Panel: Awaited<ReturnType<typeof loadPanel>>, notice: NoticeRecord) {
  return render(
    <ToastProvider>
      <Panel notice={notice} />
    </ToastProvider>,
  );
}

describe("DocumentPreparationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty-state and disables validate when no document_automation present", async () => {
    const Panel = await loadPanel();
    renderPanel(Panel, mkNotice());

    expect(screen.getByRole("heading", { name: "서류 준비" })).toBeInTheDocument();
    expect(
      screen.getByText("분석 후 체크리스트와 검토용 초안을 생성합니다."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("공고 분석이 완료된 건에서 서류 분석을 실행할 수 있습니다."),
    ).toBeInTheDocument();

    const analyzeBtn = screen.getByRole("button", { name: "서류 분석" });
    const validateBtn = screen.getByRole("button", { name: "제출 전 검증" });
    expect(analyzeBtn).toBeEnabled(); // status=analyzed → analyze allowed
    expect(validateBtn).toBeDisabled(); // no docs yet
  });

  it("disables 서류 분석 when notice.status is collected", async () => {
    const Panel = await loadPanel();
    renderPanel(Panel, mkNotice({ status: "collected" }));

    expect(screen.getByRole("button", { name: "서류 분석" })).toBeDisabled();
  });

  it("renders checklist rows and risks when document_automation is present", async () => {
    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [
        mkItem({ id: "bid_form", name: "입찰참가신청서", status: "generated", type: "bid_form" }),
        mkItem({ id: "biz", name: "사업자등록증", status: "needed", type: "company_common" }),
      ],
      drafts: {
        technical_compliance: { kind: "markdown", label: "규격대응표 초안", content: "| a | b |" },
      },
      risks: ["마감 임박"],
      generated_at: "2026-06-03T08:00:00+00:00",
      source: "rule+llm",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    expect(screen.getByText("입찰참가신청서")).toBeInTheDocument();
    expect(screen.getByText("사업자등록증")).toBeInTheDocument();
    expect(screen.getByText("규격대응표 초안")).toBeInTheDocument();
    expect(screen.getByText("위험/확인 메모")).toBeInTheDocument();
    expect(screen.getByText("마감 임박")).toBeInTheDocument();
    // summary line contains source
    expect(screen.getByText(/source: rule\+llm/)).toBeInTheDocument();
  });

  it("calls actionUpdateDocumentChecklistItem when a status select changes", async () => {
    const { actionUpdateDocumentChecklistItem } = await import("@/lib/actions");
    (actionUpdateDocumentChecklistItem as ReturnType<typeof vi.fn>).mockResolvedValue({
      notice_no: "DOC-1",
      document_automation: {
        checklist: [],
        drafts: {},
        risks: [],
        generated_at: "",
        source: "rule",
        ready_for_submission: false,
        missing_required: [],
        errors: [],
      },
    });

    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [mkItem({ id: "bid_form", name: "입찰참가신청서" })],
      drafts: {},
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    const row = screen.getByText("입찰참가신청서").closest("tr");
    expect(row).not.toBeNull();
    const select = within(row as HTMLElement).getByRole("combobox");
    fireEvent.change(select, { target: { value: "ready" } });

    expect(actionUpdateDocumentChecklistItem).toHaveBeenCalledWith(
      "DOC-1",
      "bid_form",
      { status: "ready" },
    );
  });

  it("calls actionValidateDocuments when 제출 전 검증 is clicked", async () => {
    const { actionValidateDocuments } = await import("@/lib/actions");
    (actionValidateDocuments as ReturnType<typeof vi.fn>).mockResolvedValue({
      notice_no: "DOC-1",
      ready_for_submission: true,
      missing_required: [],
      checklist: [],
    });

    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [mkItem({ id: "a" })],
      drafts: {},
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    fireEvent.click(screen.getByRole("button", { name: "제출 전 검증" }));
    expect(actionValidateDocuments).toHaveBeenCalledWith("DOC-1");
  });

  it("calls actionAnalyzeDocuments when 서류 분석 is clicked", async () => {
    const { actionAnalyzeDocuments } = await import("@/lib/actions");
    (actionAnalyzeDocuments as ReturnType<typeof vi.fn>).mockResolvedValue({
      notice_no: "DOC-1",
      document_automation: {
        checklist: [],
        drafts: {},
        risks: [],
        generated_at: "",
        source: "rule",
        ready_for_submission: false,
        missing_required: [],
        errors: [],
      },
    });

    const Panel = await loadPanel();
    renderPanel(Panel, mkNotice());

    fireEvent.click(screen.getByRole("button", { name: "서류 분석" }));
    expect(actionAnalyzeDocuments).toHaveBeenCalledWith("DOC-1");
  });
});
