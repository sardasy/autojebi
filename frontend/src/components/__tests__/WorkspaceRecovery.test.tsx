import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QuoteRecovery, SourceNeeds } from "../WorkspaceRecovery";
import { Workspace, WorkspaceJob, workspaceApi } from "@/lib/workspace";

vi.mock("@/lib/workspace", async importOriginal => ({...await importOriginal<typeof import("@/lib/workspace")>(), workspaceApi: vi.fn()}));
const ws = {version: 9, source_changed: false, inputs: {documents: [{id: "d", name: "notice", role: "notice_source", text: "납기 90일"}], requirements: []}} as unknown as Workspace;
const job = {id: "j", kind: "analyze", status: "failed", result: {quote_diagnostics: [{candidate_id: "0", status: "whitespace", requirement: {text: "납기", quote: "납기\n90일", document_id: "d", locator: "1절", category: "schedule", mandatory: true}, matches: [{start: 0, end: 6, quote: "납기 90일"}]}]}} as WorkspaceJob;

describe("source recovery", () => {
  beforeEach(() => vi.mocked(workspaceApi).mockReset().mockResolvedValue({}));
  it("requires an explicit note and adopts without approval", async () => {
    render(<QuoteRecovery job={job} ws={ws} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("공백 차이 · 납기"));
    expect(screen.getByRole("button", {name: "이 후보 채택"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "대조함"}});
    fireEvent.click(screen.getByRole("button", {name: "이 후보 채택"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/N/jobs/j/adopt-requirements", expect.objectContaining({version: 9, items: [{candidate_id: "0", quote: "납기 90일", start: 0, locator: "1절"}]})));
  });
  it("does not auto-select ambiguous positions", () => {
    const multiple = {...job, result: {quote_diagnostics: [{...job.result!.quote_diagnostics![0], status: "ambiguous" as const, matches: [{start: 0, end: 6, quote: "납기 90일"}, {start: 7, end: 13, quote: "납기 90일"}]}]}};
    render(<QuoteRecovery job={multiple} ws={ws} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("위치 중복 · 납기"));
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "대조함"}});
    expect(screen.getByRole("button", {name: "이 후보 채택"})).toBeDisabled();
  });
  it("displays missing referenced documents and uses versioned PUT", async () => {
    const value = {...ws, source_needs: [{id: "need", name: "제안요청서", state: "missing" as const, linked_document_id: "", note: "", resolution_quote: "", mentions: []}]};
    render(<SourceNeeds ws={value} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("제안요청서 · 확보·해당 여부 확인 필요"));
    fireEvent.change(screen.getByLabelText("확인 의견"), {target: {value: "미확보"}});
    fireEvent.click(screen.getByRole("button", {name: "문서 확인 저장"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/N/source-needs", expect.objectContaining({version: 9}), "PUT"));
  });
});
