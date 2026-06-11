import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ToastProvider } from "../Toast";
import type { NoticeRecord } from "@/lib/api";

vi.mock("@/lib/actions", () => ({
  actionAnalyze: vi.fn(),
}));

async function loadBar() {
  const mod = await import("../NoticeActionsBar");
  return mod.NoticeActionsBar;
}

function buildNotice(status: string): NoticeRecord {
  return {
    notice_no: "T",
    title: "x",
    source: "TEST",
    raw: null,
    category: "ABB장비",
    fit_score: 0,
    assignee: "x",
    analysis: {},
    status,
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
}

describe("NoticeActionsBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("status='collected' → 분석만 활성, 그레이드 비활성", async () => {
    const Bar = await loadBar();
    render(
      <ToastProvider>
        <Bar notice={buildNotice("collected")} />
      </ToastProvider>,
    );
    expect(screen.getByRole("button", { name: "분석" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "그레이드" })).toBeDisabled();
  });

  it("status='analyzed' → 분석 비활성, 그레이드 활성", async () => {
    const Bar = await loadBar();
    render(
      <ToastProvider>
        <Bar notice={buildNotice("analyzed")} />
      </ToastProvider>,
    );
    expect(screen.getByRole("button", { name: "분석" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "그레이드" })).not.toBeDisabled();
  });

  it("숨긴 버튼(알림·HWP 양식)이 렌더되지 않음", async () => {
    const Bar = await loadBar();
    render(
      <ToastProvider>
        <Bar notice={buildNotice("analyzed")} />
      </ToastProvider>,
    );
    expect(screen.queryByRole("button", { name: "알림" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "HWP 양식" }),
    ).not.toBeInTheDocument();
  });
});
