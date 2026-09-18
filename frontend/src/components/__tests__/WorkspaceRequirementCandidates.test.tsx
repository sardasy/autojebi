import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {Workspace, workspaceApi} from "@/lib/workspace";
import WorkspaceRequirementCandidates from "../WorkspaceRequirementCandidates";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
const quote = "수량 3대, 예비 장비는 포함하지 않는다.";
const text = `📌 안내\n${quote}`;
const ws = {version: 4, source_changed: false, inputs: {documents: [{id: "d", role: "notice_source", name: "원문", text}], requirements: []}} as unknown as Workspace;
const candidate = {id: "c", document_id: "d", document_name: "원문", document_sha256: "a".repeat(64), source_text_sha256: "b".repeat(64), text: quote, quote, start: 5, end: 5 + Array.from(quote).length, locator: "본문 2행", category: "technical", signals: ["수량", "의무·제한"]};
const result = {version: 4, items: [candidate], warnings: [], limited: false, scanned_characters: text.length, source_document_count: 1};

async function discover(container: HTMLElement) {
  fireEvent.click(screen.getByRole("button", {name: "원문에서 요구사항 후보 찾기"}));
  await waitFor(() => expect(container.querySelector("details")).not.toBeNull());
  const details = container.querySelector("details")!;
  details.open = true; fireEvent(details, new Event("toggle"));
  await screen.findByRole("button", {name: "검토 대기 요구사항으로 저장"});
}

describe("deterministic requirement recovery", () => {
  beforeEach(() => vi.mocked(workspaceApi).mockReset().mockResolvedValue(result));
  it("only reads on explicit request and requires source review before storing an unchanged pending quote", async () => {
    const reload = vi.fn();
    const {container} = render(<WorkspaceRequirementCandidates ws={ws} prefix="/notices/N" reload={reload}/>);
    expect(workspaceApi).not.toHaveBeenCalled();
    await discover(container);
    expect(workspaceApi).toHaveBeenCalledWith("/notices/N/requirement-candidates?version=4");
    const save = screen.getByRole("button", {name: "검토 대기 요구사항으로 저장"});
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByLabelText("앞뒤 문맥과 숫자·단위·부정 표현을 확인했습니다"));
    vi.mocked(workspaceApi).mockResolvedValueOnce({});
    fireEvent.click(save);
    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(workspaceApi).toHaveBeenLastCalledWith("/notices/N/requirements", {
      version: 4, document_id: "d", text: quote, quote, locator: "본문 2행", category: "technical", mandatory: true,
      review_status: "pending", compliance: "unassessed",
    });
    expect(save).toBeDisabled();
  });
  it.each(["duplicate", "mismatch", "missing", "reference", "stale"])("blocks %s candidates, including direct submit", async reason => {
    const changed = {...ws, inputs: {...ws.inputs,
      documents: reason === "missing" ? [] : [{...ws.inputs.documents[0], text: reason === "mismatch" ? "다른 원문" : text, role: reason === "reference" ? "company_reference" as const : "notice_source" as const}],
      requirements: reason === "duplicate" ? [{document_id: "d", quote, text: quote}] as Workspace["inputs"]["requirements"] : [],
    }};
    if (reason === "stale") vi.mocked(workspaceApi).mockResolvedValueOnce({...result, version: 3});
    const {container} = render(<WorkspaceRequirementCandidates ws={changed} prefix="/notices/N" reload={vi.fn()}/>);
    await discover(container);
    fireEvent.click(screen.getByLabelText("앞뒤 문맥과 숫자·단위·부정 표현을 확인했습니다"));
    const save = screen.getByRole("button", {name: "검토 대기 요구사항으로 저장"});
    expect(save).toBeDisabled(); fireEvent.submit(save.closest("form")!);
    expect(workspaceApi).toHaveBeenCalledTimes(1);
  });
  it("discards valid positions when a newer input version arrives", async () => {
    const props = {prefix: "/notices/N", reload: vi.fn()};
    const {container, rerender} = render(<WorkspaceRequirementCandidates {...props} ws={ws}/>);
    await discover(container);
    fireEvent.click(screen.getByLabelText("앞뒤 문맥과 숫자·단위·부정 표현을 확인했습니다"));
    expect(screen.getByRole("button", {name: "검토 대기 요구사항으로 저장"})).toBeEnabled();
    rerender(<WorkspaceRequirementCandidates {...props} ws={{...ws, version: 5}}/>);
    expect(screen.getByRole("button", {name: "검토 대기 요구사항으로 저장"})).toBeDisabled();
    expect(screen.getByText("입력이 변경되었습니다. 현재 원문에서 후보를 다시 찾으세요.")).toBeInTheDocument();
  });
});
