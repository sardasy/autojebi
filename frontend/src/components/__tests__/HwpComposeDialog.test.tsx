import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NoticeRecord, NoticeSpecItem } from "@/lib/api";
import { ToastProvider } from "../Toast";

vi.mock("@/lib/actions", () => ({
  actionComposeHwpDocuments: vi.fn(),
  actionGetHwpAgentHealth: vi.fn(),
}));

async function loadDialog() {
  const mod = await import("../HwpComposeDialog");
  return mod.HwpComposeDialog;
}

const notice: NoticeRecord = {
  notice_no: "DOC-1",
  title: "테스트 공고",
  source: "G2B",
  raw: null,
  category: "ABB장비",
  fit_score: 80,
  assignee: "이용문",
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

const specItems: NoticeSpecItem[] = [
  {
    id: 1,
    notice_no: "DOC-1",
    item_key: "rated_voltage",
    label: "정격전압",
    required_value: "22.9",
    proposed_value: "22.9kV 대응",
    unit: "kV",
    category: "technical",
    source: "rule",
    confidence: 0.8,
    evidence: {},
    status: "matched",
    sort_order: 1,
    created_at: null,
    updated_at: null,
  },
];

function renderDialog(Dialog: Awaited<ReturnType<typeof loadDialog>>) {
  return render(
    <ToastProvider>
      <Dialog open={true} onClose={() => {}} notice={notice} specItems={specItems} />
    </ToastProvider>,
  );
}

describe("HwpComposeDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows HWP agent unavailable state", async () => {
    const { actionGetHwpAgentHealth } = await import("@/lib/actions");
    (actionGetHwpAgentHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      base_url: "http://hwp-agent.test",
      detail: "down",
    });
    const Dialog = await loadDialog();

    renderDialog(Dialog);

    expect(await screen.findByText(/미연결 또는 비정상/)).toBeInTheDocument();
  });

  it("keeps compose errors visible in the dialog", async () => {
    const { actionComposeHwpDocuments, actionGetHwpAgentHealth } = await import("@/lib/actions");
    (actionGetHwpAgentHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      base_url: "http://hwp-agent.test",
      detail: null,
    });
    (actionComposeHwpDocuments as ReturnType<typeof vi.fn>).mockResolvedValue({
      notice_no: "DOC-1",
      status: "analyzed",
      bid_form: null,
      technical_compliance: null,
      remaining_placeholders: [],
      errors: [{ stage: "technical_compliance", detail: "agent down" }],
    });
    const Dialog = await loadDialog();
    renderDialog(Dialog);

    fireEvent.click(screen.getByRole("button", { name: "작성" }));

    await waitFor(() =>
      expect(actionComposeHwpDocuments).toHaveBeenCalledWith(
        "DOC-1",
        expect.objectContaining({ include_technical_compliance: true }),
      ),
    );
    expect(await screen.findByText("HWP 작성 오류")).toBeInTheDocument();
    expect(screen.getByText(/technical_compliance: agent down/)).toBeInTheDocument();
  });
});
