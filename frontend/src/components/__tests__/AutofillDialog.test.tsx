import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ToastProvider } from "../Toast";
import type { NoticeRecord } from "@/lib/api";

vi.mock("@/lib/actions", () => ({
  actionAutofill: vi.fn(),
}));

// Lazy import after mocks are registered
async function loadDialog() {
  const mod = await import("../AutofillDialog");
  return mod.AutofillDialog;
}

const fakeNotice: NoticeRecord = {
  notice_no: "T1-00",
  title: "테스트",
  source: "TEST",
  raw: null,
  category: "ABB장비",
  fit_score: 0,
  assignee: "x",
  analysis: {},
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
};

describe("AutofillDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects path with traversal '..'", async () => {
    const AutofillDialog = await loadDialog();
    render(
      <ToastProvider>
        <AutofillDialog open={true} onClose={() => {}} notice={fakeNotice} />
      </ToastProvider>,
    );
    const templateInput = screen.getByDisplayValue(/templates\/입찰참가신청서/);
    fireEvent.change(templateInput, { target: { value: "../etc/passwd" } });
    // 검증 에러 노출
    expect(screen.getByText(/template_path는 상대 경로/)).toBeInTheDocument();
  });

  it("rejects absolute Windows path", async () => {
    const AutofillDialog = await loadDialog();
    render(
      <ToastProvider>
        <AutofillDialog open={true} onClose={() => {}} notice={fakeNotice} />
      </ToastProvider>,
    );
    const templateInput = screen.getByDisplayValue(/templates/);
    fireEvent.change(templateInput, { target: { value: "C:\\Windows\\evil.hwp" } });
    expect(screen.getByText(/template_path는 상대 경로/)).toBeInTheDocument();
  });

  it("rejects invalid JSON in values", async () => {
    const AutofillDialog = await loadDialog();
    render(
      <ToastProvider>
        <AutofillDialog open={true} onClose={() => {}} notice={fakeNotice} />
      </ToastProvider>,
    );
    const valuesArea = screen.getByText(/values \(JSON/).nextElementSibling as HTMLTextAreaElement;
    fireEvent.change(valuesArea, { target: { value: "{not valid" } });
    expect(screen.getByText(/values JSON 파싱 실패/)).toBeInTheDocument();
  });

  it("uses bid_form_values draft as default JSON", async () => {
    const AutofillDialog = await loadDialog();
    render(
      <ToastProvider>
        <AutofillDialog
          open={true}
          onClose={() => {}}
          notice={{
            ...fakeNotice,
            analysis: {
              document_automation: {
                checklist: [],
                drafts: {
                  bid_form_values: {
                    values: {
                      org_name: "한국전력",
                      top_sku_name: "ABB-X1",
                    },
                  },
                },
                risks: [],
                generated_at: "",
                source: "rule",
                ready_for_submission: false,
                missing_required: [],
                errors: [],
              },
            },
          }}
        />
      </ToastProvider>,
    );
    const valuesArea = screen.getByText(/values \(JSON/).nextElementSibling as HTMLTextAreaElement;
    expect(valuesArea.value).toContain('"org_name": "한국전력"');
    expect(valuesArea.value).toContain('"top_sku_name": "ABB-X1"');
  });
});
