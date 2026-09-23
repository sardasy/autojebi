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
const attachmentOnly: Workspace = {...ws, writing_plan_current: true, inputs: {...ws.inputs,
  writing_plan: {reviewed_at: "2026-09-20", reviewed_version: 5, items: [
    {id: "issued", title: "사업자등록증", document_id: "source", quote: "사업자등록증", action: "attach", document_kind: "other_document"},
    {id: "electronic", title: "입찰서", document_id: "source", quote: "입찰서", action: "electronic", document_kind: "bid_document"},
  ]},
}};

describe("output plan and participation", () => {
  beforeEach(() => {vi.clearAllMocks();});
  it("explicitly omits HWP for a reviewed attachment-only plan even without installed templates", async () => {
    const onSaved = vi.fn(); vi.mocked(workspaceApi).mockResolvedValue({...attachmentOnly, version: 6});
    render(<WorkspaceOutputPlan ws={attachmentOnly} prefix="/notices/PLAN" templates={[]} busy={false} onSaved={onSaved}/>);
    fireEvent.click(screen.getByRole("checkbox", {name: /HWP 생성 불필요/}));
    expect(screen.getByRole("button", {name: "출력 서류 계획 저장"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("출력 서류 확인 의견"), {target: {value: "공고상 원본 첨부와 전자 제출만 필요"}});
    fireEvent.click(screen.getByRole("button", {name: "출력 서류 계획 저장"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/PLAN/output-plan", {
      version: 5, template_keys: [], note: "공고상 원본 첨부와 전자 제출만 필요",
    }, "PUT"));
    expect(screen.getByText(/전자 제출은 담당자가 직접 수행합니다/)).toBeInTheDocument();
  });
  it.each(["source", "stale", "empty", "write"])("rejects a saved empty plan after %s invalidation", invalid => {
    const changed = structuredClone(attachmentOnly);
    changed.inputs.output_plan = {template_keys: [], note: "이전 확인"};
    if (invalid === "source") changed.source_changed = true;
    else if (invalid === "stale") changed.writing_plan_current = false;
    else if (invalid === "empty") changed.inputs.writing_plan!.items = [];
    else changed.inputs.writing_plan!.items[0].action = "write";
    render(<WorkspaceOutputPlan ws={changed} prefix="/notices/PLAN" templates={templates} busy={false} onSaved={vi.fn()}/>);
    expect(screen.queryByText(/HWP 생성 불필요 ·/)).not.toBeInTheDocument();
    expect(screen.getByText("출력 서류 계획 저장")).toBeDisabled();
    expect(workspaceApi).not.toHaveBeenCalled();
  });
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
