import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { NoticeRecord } from "@/lib/api";
import { BidWorkflowRail } from "../BidWorkflowRail";

function mkNotice(overrides: Partial<NoticeRecord> = {}): NoticeRecord {
  return {
    notice_no: "T1",
    title: "테스트 공고",
    source: "TEST",
    raw: null,
    category: "ABB장비",
    fit_score: 80,
    assignee: "미배정",
    analysis: {},
    status: "collected",
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
    unresolved_error_count: 0,
    export_count: 0,
    spec_item_count: 0,
    ...overrides,
  };
}

describe("BidWorkflowRail", () => {
  it("renders the bid operation steps and next action", () => {
    render(<BidWorkflowRail notice={mkNotice()} />);

    expect(screen.getByRole("heading", { name: "입찰 업무 흐름" })).toBeInTheDocument();
    expect(screen.getByText(/다음 작업:/)).toBeInTheDocument();
    expect(screen.getAllByText("공고 분석 필요").length).toBeGreaterThan(0);
    expect(screen.getByText("공고 검토")).toBeInTheDocument();
    expect(screen.getByText("서류 준비")).toBeInTheDocument();
    expect(screen.getByText("규격 항목")).toBeInTheDocument();
    expect(screen.getByText("규격대응표")).toBeInTheDocument();
    expect(screen.getByText("제안서 초안")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "분석/그레이드로 이동" })).toHaveAttribute(
      "href",
      "#work-actions",
    );
    expect(screen.getByRole("link", { name: "서류 준비로 이동" })).toHaveAttribute(
      "href",
      "#documents",
    );
    expect(screen.getByRole("link", { name: "규격 항목으로 이동" })).toHaveAttribute(
      "href",
      "#spec-items",
    );
    expect(screen.getByRole("link", { name: "규격대응표 작성으로 이동" })).toHaveAttribute(
      "href",
      "#spec-items",
    );
    expect(screen.getByRole("link", { name: "제안서 작성으로 이동" })).toHaveAttribute(
      "href",
      "#spec-items",
    );
  });

  it("marks proposal step done when proposal draft and compliance export exist", () => {
    render(
      <BidWorkflowRail
        notice={mkNotice({
          status: "hwp_composed",
          graded_at: "2026-06-22T00:00:00+09:00",
          spec_item_count: 3,
          analysis: {
            document_automation: {
              checklist: [
                {
                  id: "technical_compliance",
                  name: "규격대응표",
                  type: "technical",
                  required: true,
                  status: "generated",
                  owner: null,
                  reason: null,
                  source: "rule",
                  due_hint: null,
                },
              ],
              drafts: {
                technical_compliance: { kind: "markdown", content: "x" },
                proposal: { kind: "hwp_proposal", values: {} },
              },
              risks: [],
              generated_at: "",
              source: "rule",
              ready_for_submission: true,
              missing_required: [],
              errors: [],
              exports: [
                {
                  kind: "excel",
                  draft_id: "technical_compliance",
                  output_path: "x.xlsx",
                  mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  generated_at: "2026-06-22T00:00:00+09:00",
                },
              ],
            },
          },
        })}
      />,
    );

    expect(screen.getAllByText("완료").length).toBeGreaterThanOrEqual(5);
    expect(screen.getByText("초안/파일 생성됨")).toBeInTheDocument();
    expect(screen.getByText(/최종 검토 가능/)).toBeInTheDocument();
  });
});
