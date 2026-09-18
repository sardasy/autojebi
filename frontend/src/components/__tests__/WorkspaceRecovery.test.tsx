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
    const repeated = {...ws, inputs: {...ws.inputs, documents: [{...ws.inputs.documents[0], text: "납기 90일\n납기 90일"}]}};
    render(<QuoteRecovery job={multiple} ws={repeated} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("위치 중복 · 납기"));
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "대조함"}});
    expect(screen.getByRole("button", {name: "이 후보 채택"})).toBeDisabled();
  });
  it("finds a corrected quote in the current source and preserves numbers, negation and Unicode offsets", async () => {
    const quote = "수량 3대, 제외하지 않음.\n납기 90일";
    const value = {...ws, inputs: {...ws.inputs, documents: [{...ws.inputs.documents[0], text: `📌 공고\n${quote}`}]}};
    const failed = {...job, result: {quote_diagnostics: [{...job.result!.quote_diagnostics![0], status: "mismatch" as const, matches: []}]}};
    render(<QuoteRecovery job={failed} ws={value} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("불일치 · 납기"));
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "원문 그대로 교정"}});
    const adopt = screen.getByRole("button", {name: "이 후보 채택"});
    expect(adopt).toBeDisabled();
    fireEvent.change(screen.getByLabelText("교정 인용"), {target: {value: quote}});
    expect(screen.getByRole("status")).toHaveTextContent("정확히 일치하는 위치 1곳");
    expect(screen.queryByLabelText("원문 시작 위치")).not.toBeInTheDocument();
    expect(adopt).toBeEnabled();
    fireEvent.click(adopt);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      items: [{candidate_id: "0", quote, start: 5, locator: "1절"}],
    })));
  });
  it("requires contextual selection for every repeated quote and clears it after edits", async () => {
    const value = {...ws, inputs: {...ws.inputs, documents: [{...ws.inputs.documents[0], text: "1차 납기 90일\n2차 납기 90일"}]}};
    render(<QuoteRecovery job={job} ws={value} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("공백 차이 · 납기"));
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "2차 문맥 확인"}});
    const adopt = screen.getByRole("button", {name: "이 후보 채택"});
    expect(adopt).toBeDisabled();
    expect(screen.getByRole("option", {name: /2번째 · 2행/})).toHaveTextContent("2차 납기 90일");
    fireEvent.change(screen.getByLabelText("원문 위치 선택"), {target: {value: "13"}});
    expect(adopt).toBeEnabled();
    fireEvent.change(screen.getByLabelText("교정 인용"), {target: {value: "납기 9일"}});
    expect(adopt).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("정확히 일치하는 원문이 없습니다");
    fireEvent.change(screen.getByLabelText("교정 인용"), {target: {value: "납기 90일"}});
    expect(adopt).toBeDisabled();
    fireEvent.change(screen.getByLabelText("원문 위치 선택"), {target: {value: "13"}});
    fireEvent.click(adopt);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      items: [{candidate_id: "0", quote: "납기 90일", start: 13, locator: "1절"}],
    })));
  });
  it("keeps whitespace variants selectable and locates the chosen quote without manual offsets", async () => {
    const value = {...ws, inputs: {...ws.inputs, documents: [{...ws.inputs.documents[0], text: "납기 90일\n납기\t90일"}]}};
    const variants = {...job, result: {quote_diagnostics: [{...job.result!.quote_diagnostics![0], matches: [
      {start: 0, end: 6, quote: "납기 90일"}, {start: 7, end: 13, quote: "납기\t90일"},
    ]}]}};
    render(<QuoteRecovery job={variants} ws={value} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText("공백 차이 · 납기"));
    fireEvent.change(screen.getByLabelText("원문 인용 후보"), {target: {value: "납기\t90일"}});
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "두 번째 인용 확인"}});
    fireEvent.click(screen.getByRole("button", {name: "이 후보 채택"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      items: [{candidate_id: "0", quote: "납기\t90일", start: 7, locator: "1절"}],
    })));
  });
  it.each(["missing", "empty", "reference", "changed", "duplicate"])("blocks adoption with %s source state, including direct form submission", state => {
    const value = {...ws, source_changed: state === "changed", inputs: {...ws.inputs,
      documents: state === "missing" ? [] : [{...ws.inputs.documents[0],
        text: state === "empty" ? "" : "납기 90일",
        role: state === "reference" ? "company_reference" as const : "notice_source" as const,
      }],
      requirements: state === "duplicate" ? [{...job.result!.quote_diagnostics![0].requirement, id: "existing"}] as Workspace["inputs"]["requirements"] : [],
    }};
    render(<QuoteRecovery job={job} ws={value} prefix="/notices/N" reload={vi.fn()}/>);
    fireEvent.click(screen.getByText(/공백 차이 · 납기/));
    fireEvent.change(screen.getByLabelText("채택 의견"), {target: {value: "대조함"}});
    const adopt = screen.getByRole("button", {name: "이 후보 채택"});
    expect(adopt).toBeDisabled();
    fireEvent.submit(adopt.closest("form")!);
    expect(workspaceApi).not.toHaveBeenCalled();
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
