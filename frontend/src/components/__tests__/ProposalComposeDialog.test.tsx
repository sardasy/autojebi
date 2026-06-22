import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NoticeRecord, NoticeSpecItem } from "@/lib/api";
import { ToastProvider } from "../Toast";

vi.mock("@/lib/actions", () => ({
  actionComposeProposalDocument: vi.fn(),
  actionGetHwpAgentHealth: vi.fn(),
}));

async function loadDialog() {
  const mod = await import("../ProposalComposeDialog");
  return mod.ProposalComposeDialog;
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
  org_name: "한국전력공사",
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
  top_sku_name: "ABB-TEST",
  sku_match_score: null,
  graded_at: null,
};

const specItems: NoticeSpecItem[] = [
  {
    id: 1,
    notice_no: "DOC-1",
    item_key: "rated_voltage_kv",
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

function renderDialog(Dialog: Awaited<ReturnType<typeof loadDialog>>, items = specItems) {
  return render(
    <ToastProvider>
      <Dialog open={true} onClose={() => {}} notice={notice} specItems={items} />
    </ToastProvider>,
  );
}

function routerRefreshMock() {
  return (globalThis as typeof globalThis & {
    __routerRefreshMock: ReturnType<typeof vi.fn>;
  }).__routerRefreshMock;
}

describe("ProposalComposeDialog", () => {
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

  it("blocks compose when spec items are missing", async () => {
    const { actionGetHwpAgentHealth } = await import("@/lib/actions");
    (actionGetHwpAgentHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      base_url: "http://hwp-agent.test",
      detail: null,
    });
    const Dialog = await loadDialog();

    renderDialog(Dialog, []);

    expect(await screen.findByText(/규격 추출 필요/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "작성" })).toBeDisabled();
  });

  it("shows proposal section preview and spec item samples", async () => {
    const { actionGetHwpAgentHealth } = await import("@/lib/actions");
    (actionGetHwpAgentHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      base_url: "http://hwp-agent.test",
      detail: null,
    });
    const Dialog = await loadDialog();

    renderDialog(Dialog, [
      {
        ...specItems[0],
        status: "candidate",
        review_priority: "high",
        confidence: 0.5,
      },
    ]);

    expect(await screen.findByText("생성 섹션")).toBeInTheDocument();
    expect(screen.getByText("회사 소개")).toBeInTheDocument();
    expect(screen.getByText("규격 대응 요약")).toBeInTheDocument();
    expect(screen.getByText("규격 대응 샘플")).toBeInTheDocument();
    expect(screen.getByText(/정격전압: 22.9kV 대응/)).toBeInTheDocument();
    expect(screen.getByText(/검토 우선 항목 1개: 정격전압/)).toBeInTheDocument();
  });

  it("keeps proposal compose errors visible", async () => {
    const { actionComposeProposalDocument, actionGetHwpAgentHealth } = await import("@/lib/actions");
    (actionGetHwpAgentHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      base_url: "http://hwp-agent.test",
      detail: null,
    });
    (actionComposeProposalDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      notice_no: "DOC-1",
      export: null,
      proposal: {},
      remaining_placeholders: ["company_name"],
      errors: [{ stage: "proposal", detail: "agent down" }],
    });
    const Dialog = await loadDialog();
    renderDialog(Dialog);

    fireEvent.click(screen.getByRole("button", { name: "작성" }));

    await waitFor(() =>
      expect(actionComposeProposalDocument).toHaveBeenCalledWith(
        "DOC-1",
        expect.objectContaining({
          template_path: "templates/제안서_양식.hwp",
          values_override: {},
          visible: false,
        }),
      ),
    );
    expect(routerRefreshMock()).toHaveBeenCalled();
    expect(await screen.findByText("제안서 작성 오류")).toBeInTheDocument();
    expect(screen.getByText(/proposal: agent down/)).toBeInTheDocument();
    expect(screen.getByText(/남은 placeholder 1개/)).toBeInTheDocument();
  });
});
