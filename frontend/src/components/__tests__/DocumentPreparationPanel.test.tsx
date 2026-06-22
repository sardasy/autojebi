import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../Toast";
import type {
  DocumentAutomationResult,
  DocumentChecklistItem,
  NoticeRecord,
} from "@/lib/api";

vi.mock("@/lib/actions", () => ({
  actionAnalyzeDocuments: vi.fn(),
  actionComposeHwpDocuments: vi.fn(),
  actionExtractSpecItems: vi.fn(),
  actionExportDocument: vi.fn(),
  actionFetchG2BAttachments: vi.fn(),
  actionGetHwpAgentHealth: vi.fn().mockResolvedValue({ ok: false, base_url: "http://hwp" }),
  actionImportCommonUpload: vi.fn(),
  actionListSpecItems: vi.fn().mockResolvedValue({ notice_no: "DOC-1", items: [] }),
  actionListCommonUploads: vi.fn().mockResolvedValue({ items: [] }),
  actionUpdateSpecItem: vi.fn(),
  actionUpdateDocumentChecklistItem: vi.fn(),
  actionUploadCommonDocument: vi.fn(),
  actionValidateDocuments: vi.fn(),
}));

vi.mock("../SpecItemsPanel", () => ({
  SpecItemsPanel: () => <div data-testid="spec-items-panel">규격 항목</div>,
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

  it("allows document re-analysis for advanced workflow statuses", async () => {
    const Panel = await loadPanel();
    renderPanel(Panel, mkNotice({ status: "hwp_composed" }));

    expect(screen.getByRole("button", { name: "서류 분석" })).toBeEnabled();
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

  it("shows remaining HWP placeholders when bid_form draft has them", async () => {
    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [mkItem({ id: "bid_form", name: "입찰참가신청서" })],
      drafts: {
        bid_form: {
          remaining_placeholders: ["company_name", "ceo_name"],
        },
      },
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    expect(screen.getByText(/남은 HWP 입력값 2개/)).toBeInTheDocument();
  });

  it("shows persisted document automation errors", async () => {
    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [mkItem({ id: "technical_compliance", name: "규격대응표" })],
      drafts: {},
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [
        {
          stage: "proposal",
          detail: "HWP agent unavailable",
          severity: "error",
        },
        {
          stage: "attachment.fetch",
          detail: "download failed",
          file_name: "spec.pdf",
          severity: "warning",
        },
      ],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    expect(screen.getByText("서류 처리 오류 2건")).toBeInTheDocument();
    expect(
      screen.getAllByText((_, element) =>
        Boolean(element?.textContent?.includes("proposal: HWP agent unavailable")),
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText((_, element) =>
        Boolean(element?.textContent?.includes("attachment.fetch · spec.pdf: download failed")),
      ).length,
    ).toBeGreaterThan(0);
  });

  it("shows export quality metadata and export_id download links", async () => {
    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [mkItem({ id: "technical_compliance", name: "규격대응표" })],
      drafts: {
        technical_compliance: {
          kind: "markdown",
          label: "규격대응표 초안",
          content: "| a | b |",
        },
      },
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
      exports: [
        {
          id: 17,
          kind: "excel",
          draft_id: "technical_compliance",
          output_path: "data/exports/compliance.xlsx",
          mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          generated_at: "2026-06-21T00:00:00+00:00",
          version: "compliance_excel_v2",
          validation_status: "warning",
          validation_errors: [{ stage: "pre_compose.spec_review" }],
          file_size: 2048,
          sha256: "abc",
        },
      ],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    expect(screen.getByText(/compliance_excel_v2/)).toBeInTheDocument();
    expect(screen.getByText(/검토 필요/)).toBeInTheDocument();
    expect(screen.getByText(/2KB/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "다운로드" })).toHaveAttribute(
      "href",
      "/api/notices/DOC-1/documents/exports/by-id/17/download",
    );
  });

  it("renders proposal draft sections, tables, and remaining placeholders", async () => {
    const Panel = await loadPanel();
    const docs: DocumentAutomationResult = {
      checklist: [mkItem({ id: "proposal", name: "제안서", status: "generated" })],
      drafts: {
        proposal: {
          kind: "proposal_hwp",
          label: "제안서 HWP 초안",
          values: {
            notice_no: "DOC-1",
            company_name: "미림씨스콘",
          },
          sections: [
            { title: "공고 개요", content: "기관: 한국전력공사" },
            { title: "규격 대응 요약", content: "정격전압 대응 가능" },
          ],
          tables: [
            {
              title: "규격 대응표",
              headers: ["항목", "요구사양", "제안/대응"],
              rows: [["정격전압", "22.9kV", "대응"]],
            },
          ],
          required_placeholders: ["notice_no", "company_name"],
          result: {
            remaining_placeholders: ["ceo_name"],
          },
        },
      },
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    };
    renderPanel(Panel, mkNotice({ documentAutomation: docs }));

    expect(screen.getByText("제안서 HWP 초안")).toBeInTheDocument();
    expect(screen.getByText(/섹션 2개 · 표 1개 · 필수값 2개/)).toBeInTheDocument();
    expect(screen.getByText("공고 개요")).toBeInTheDocument();
    expect(screen.getByText("기관: 한국전력공사")).toBeInTheDocument();
    expect(screen.getByText("규격 대응 요약")).toBeInTheDocument();
    expect(screen.getByText("규격 대응표")).toBeInTheDocument();
    expect(screen.getByText("정격전압")).toBeInTheDocument();
    expect(screen.getByText(/남은 placeholder 1개: ceo_name/)).toBeInTheDocument();
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

    await waitFor(() =>
      expect(actionUpdateDocumentChecklistItem).toHaveBeenCalledWith(
        "DOC-1",
        "bid_form",
        { status: "ready" },
      ),
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
    await waitFor(() => expect(actionValidateDocuments).toHaveBeenCalledWith("DOC-1"));
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
    await waitFor(() => expect(actionAnalyzeDocuments).toHaveBeenCalledWith("DOC-1"));
  });

  it("calls actionFetchG2BAttachments when 첨부 서류 가져오기 is clicked", async () => {
    const { actionFetchG2BAttachments } = await import("@/lib/actions");
    (actionFetchG2BAttachments as ReturnType<typeof vi.fn>).mockResolvedValue({
      notice_no: "DOC-1",
      fetched: [],
      errors: [],
    });

    const Panel = await loadPanel();
    renderPanel(Panel, mkNotice());

    fireEvent.click(screen.getByRole("button", { name: "첨부 서류 가져오기" }));
    await waitFor(() => expect(actionFetchG2BAttachments).toHaveBeenCalledWith("DOC-1"));
  });
});
