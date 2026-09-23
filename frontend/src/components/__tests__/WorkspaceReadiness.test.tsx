import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import type {Workspace} from "@/lib/workspace";
import WorkspaceReadiness from "../WorkspaceReadiness";

const ws: Workspace = {notice_no: "TEST", version: 3, decision: "pending", ready: false, source_changed: false,
  inputs: {notice: {title: null, org_name: null, close_date: null, base_price: null}, documents: [],
    requirements: [], checklist: [], source_reviewed: false, legacy_warning: false, company: {}},
  blockers: ["이전 응답 경고"], next_action: "", jobs: [], reviews: []};

describe("server readiness projection", () => {
  it("shows server reason, next action and evaluation version", () => {
    render(<WorkspaceReadiness ws={{...ws, readiness_checked_at: "2026-09-22T00:00:00Z", readiness_issues: [{
      code: "asset_expired", scope: "document", entity_id: "doc", blocking: true,
      message_params: {name: "실적 증명"}, message: "중앙 자료 유효기간 만료: 실적 증명", next_action: "유효한 자료를 확보하세요.",
    }]}}/>);
    expect(screen.getByText("중앙 자료 유효기간 만료: 실적 증명")).toBeInTheDocument();
    expect(screen.getByText("유효한 자료를 확보하세요.")).toBeInTheDocument();
    expect(screen.getByText(/입력 버전 3/)).toBeInTheDocument();
    expect(screen.queryByText("이전 응답 경고")).not.toBeInTheDocument();
  });
  it("supports older servers without inventing codes or approval", () => {
    render(<WorkspaceReadiness ws={ws}/>);
    expect(screen.getByText("이전 응답 경고")).toBeInTheDocument();
    expect(screen.queryByText(/준비 완료/)).not.toBeInTheDocument();
  });
});
