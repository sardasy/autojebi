import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {Workspace, workspaceApi} from "@/lib/workspace";
import WorkspaceOutputPlan from "../WorkspaceOutputPlan";
import WorkspaceDecision from "../WorkspaceDecision";

vi.mock("@/lib/workspace", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/workspace")>(), workspaceApi: vi.fn(),
}));
const ws: Workspace = {notice_no: "PLAN", version: 5, decision: "pending", ready: false, source_changed: false,
  inputs: {notice: {title: "테스트", org_name: null, close_date: null, base_price: null}, documents: [],
    requirements: [], checklist: [], source_reviewed: false, legacy_warning: false, company: {}},
  blockers: [], next_action: "", jobs: [], reviews: []};
const templates = [{template_key: "bid_form", name: "입찰참가신청서"}, {template_key: "proposal", name: "제안서"},
  {template_key: "proposal_layout_v1", name: "제안서 · 실무 서식"}];

describe("output plan and participation", () => {
  beforeEach(() => {vi.clearAllMocks();});
  it("saves the chosen real template instead of requiring both legacy placeholders", async () => {
    const onSaved = vi.fn(); const updated = {...ws, version: 6}; vi.mocked(workspaceApi).mockResolvedValue(updated);
    render(<WorkspaceOutputPlan ws={ws} prefix="/notices/PLAN" templates={templates} busy={false} onSaved={onSaved}/>);
    expect(workspaceApi).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", {name: "입찰참가신청서"}));
    fireEvent.click(screen.getByRole("checkbox", {name: /^제안서$/}));
    fireEvent.change(screen.getByLabelText("출력 서류 확인 의견"), {target: {value: "공고 요청 서식 확인"}});
    expect(screen.getByRole("button", {name: "출력 서류 계획 저장"})).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", {name: "제안서 · 실무 서식"}));
    fireEvent.click(screen.getByRole("button", {name: "출력 서류 계획 저장"}));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated));
    expect(workspaceApi).toHaveBeenCalledWith("/notices/PLAN/output-plan", {
      version: 5, template_keys: ["proposal_layout_v1"], note: "공고 요청 서식 확인",
    }, "PUT");
  });
  it("keeps conflicts visible and never silently removes a saved required template", async () => {
    const onSaved = vi.fn(); vi.mocked(workspaceApi).mockRejectedValue(new Error("입력이 변경되었습니다"));
    render(<WorkspaceOutputPlan ws={ws} prefix="/notices/PLAN" templates={templates} busy={false} onSaved={onSaved}/>);
    fireEvent.change(screen.getByLabelText("출력 서류 확인 의견"), {target: {value: "확인"}});
    fireEvent.click(screen.getByRole("button", {name: "출력 서류 계획 저장"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("입력이 변경되었습니다");
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox", {name: "입찰참가신청서"})).toBeChecked();
  });
  it("lets the reviewer explicitly record participation before output generation", async () => {
    const onSaved = vi.fn(); vi.mocked(workspaceApi).mockResolvedValue({...ws, version: 6, decision: "participate"});
    render(<WorkspaceDecision ws={ws} prefix="/notices/PLAN" busy={false} onSaved={onSaved}/>);
    expect(screen.getByRole("button", {name: "참가 결정 저장"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("참가 결정"), {target: {value: "participate"}});
    fireEvent.change(screen.getByLabelText("참가 결정 의견"), {target: {value: "참가 검토 완료"}});
    fireEvent.click(screen.getByRole("button", {name: "참가 결정 저장"}));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(workspaceApi).toHaveBeenCalledWith("/notices/PLAN/decision", {version: 5, decision: "participate", note: "참가 검토 완료"});
  });
});
