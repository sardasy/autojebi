import {render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import type {Workspace} from "@/lib/workspace";
import ReviewTab from "../workspace/ReviewTab";

vi.mock("../WorkspacePrerequisites", () => ({default: () => <p>HWP 필수조건</p>}));
vi.mock("../WorkspaceWorkerStatus", () => ({default: () => <p>문서 작업 실행기</p>}));
vi.mock("../WorkspaceHwpStatus", () => ({default: () => <p>HWP 실행기</p>}));

const ws: Workspace = {notice_no: "ATTACH", version: 3, decision: "participate", ready: false,
  source_changed: false, writing_plan_current: true, jobs: [], reviews: [], blockers: [], next_action: "",
  inputs: {notice: {title: "원본 제출", org_name: null, close_date: null, base_price: null},
    company: {}, documents: [], requirements: [], checklist: [], source_reviewed: true, legacy_warning: false,
    writing_plan: {reviewed_at: "2026-09-20", reviewed_version: 2, items: [{id: "issued", title: "사업자등록증",
      action: "attach", document_kind: "other_document", document_id: "source", quote: "사업자등록증"}]},
    output_plan: {template_keys: [], note: "원본 첨부만 필요"},
  }};

function review(value: Workspace) {
  return render(<ReviewTab ws={value} tab="4. 서류 확인" prefix="/notices/ATTACH" busy={false} note=""
    mutate={vi.fn()} run={vi.fn()} goTo={vi.fn()} setWs={vi.fn()} setStatus={vi.fn()} setFocusRequirement={vi.fn()}
    template="bid_form" setTemplate={vi.fn()} templates={[]} templateError="템플릿 없음"
    hwpVisible={false} setHwpVisible={vi.fn()} preview={null} setPreview={vi.fn()}
    prerequisites={null} setPrerequisites={vi.fn()}/>);
}

describe("attachment-only review", () => {
  it("keeps Excel and package actions without irrelevant HWP blockers or draft instructions", () => {
    review(ws);
    expect(screen.getByRole("button", {name: "Excel 생성"})).toBeEnabled();
    expect(screen.getByRole("button", {name: "검토 패키지"})).toBeEnabled();
    expect(screen.queryByText("HWP 필수조건")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "HWP 생성"})).not.toBeInTheDocument();
    expect(screen.queryByText("제안서 본문 검토")).not.toBeInTheDocument();
    expect(screen.queryByText("템플릿 없음")).not.toBeInTheDocument();
    expect(screen.getByText(/HWP 생성 불필요 확인/)).toBeInTheDocument();
  });
  it.each(["source", "plan"])("restores HWP and writing review after %s changes", change => {
    review({...ws, source_changed: change === "source", writing_plan_current: change !== "plan"});
    expect(screen.getByText("HWP 필수조건")).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "HWP 생성"})).toBeDisabled();
    expect(screen.getByText("제안서 본문 검토")).toBeInTheDocument();
  });
});
