import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import NoticeFormWorkspace from "../NoticeFormWorkspace";
import {Workspace, workspaceApi} from "@/lib/workspace";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
const makeWorkspace = (): Workspace => ({notice_no: "FORM", version: 3, decision: "pending", ready: false, source_changed: false,
  inputs: {notice: {title: "공고", org_name: null, close_date: null, base_price: null}, documents: [
    {id: "reference", name: "회사 소개서", role: "company_reference", confirmed: false, text: "전력전자 기술 지원을 제공합니다.", text_origin: "manual"},
    {id: "unconfirmed", name: "미확인 증빙", role: "company_evidence", confirmed: false, text: "미확인", text_origin: "manual"}],
  company: {}, requirements: [], checklist: [], source_reviewed: false, legacy_warning: false}, jobs: [], reviews: [], blockers: [], next_action: ""});
const catalog = {version: 3, documents: [{document_id: "template", name: "제안요청서.hwpx", sha256: "source-hash", supported: true, fields: [
  {id: "slot1", label: "회사 주요 업무", context: "서식 2: 일반현황", original: "", location: "section0/table1/row2/cell1"},
  {id: "slot2", label: "유지보수 계획", context: "서식 3: 지원 계획", original: "작성 안내", location: "section0/table1/row3/cell1"},
]}, {document_id: "pdf", name: "입찰공고.pdf", sha256: "pdf-hash", supported: false, reason: "PDF 원본은 직접 작성 대상이 아닙니다.", fields: []}], fillings: []};
const props = () => ({ws: makeWorkspace(), prefix: "/notices/FORM", busy: false, onSaved: vi.fn()});
async function loaded() {await screen.findByLabelText("양식 항목 작성 내용"); await waitFor(() => expect(screen.getByLabelText("양식 항목 작성 내용")).toBeEnabled());}
function companyReference() {
  fireEvent.change(screen.getByLabelText("참고자료 종류"), {target: {value: "company"}});
  fireEvent.change(screen.getByLabelText("참고할 회사 자료"), {target: {value: "reference"}});
  fireEvent.change(screen.getByLabelText("자료에서 발췌한 근거"), {target: {value: "전력전자 기술 지원을 제공합니다."}});
  fireEvent.click(screen.getByRole("button", {name: "발췌문을 이 항목에 넣기"}));
}
describe("notice attached form writing", () => {
  beforeEach(() => {vi.clearAllMocks(); vi.mocked(workspaceApi).mockResolvedValue(catalog);});
  it("clears a failed catalog request after a successful refresh", async () => {
    vi.mocked(workspaceApi).mockRejectedValueOnce(new Error("Not Found"));
    render(<NoticeFormWorkspace {...props()}/>);
    expect(await screen.findByText("Not Found")).toHaveAttribute("role", "status");
    await waitFor(() => expect(screen.getByRole("button", {name: "양식 목록 새로고침"})).toBeEnabled());
    fireEvent.click(screen.getByRole("button", {name: "양식 목록 새로고침"}));
    await loaded();
    expect(screen.queryByText("Not Found")).not.toBeInTheDocument();
    expect(screen.getByRole("button", {name: /1\. 회사 주요 업무/})).toBeInTheDocument();
    expect(workspaceApi).toHaveBeenCalledTimes(2);
  });
  it("saves each original slot with its source and exposes the filled original format after readback", async () => {
    const p = props();
    const view = render(<NoticeFormWorkspace {...p}/>);
    await loaded(); companyReference();
    expect(screen.queryByRole("option", {name: "미확인 증빙"})).not.toBeInTheDocument();
    expect(screen.queryByText("section0/table1/row2/cell1")).not.toBeInTheDocument();
    const saved = {document_id: "template", source_sha256: "source-hash", fields: [{field_id: "slot1", value: "전력전자 기술 지원을 제공합니다.", reference: {document_id: "reference", quote: "전력전자 기술 지원을 제공합니다."}}, {field_id: "slot2", value: ""}], input_version: 4, review_status: "pending"};
    const updated = {...p.ws, version: 4, inputs: {...p.ws.inputs, form_fillings: [saved]}};
    vi.mocked(workspaceApi).mockResolvedValueOnce(updated);
    fireEvent.click(screen.getByRole("button", {name: "양식 초안 저장"}));
    await waitFor(() => expect(p.onSaved).toHaveBeenCalledWith(updated));
    const [path, body] = vi.mocked(workspaceApi).mock.calls[1];
    expect(path).toBe("/notices/FORM/form-fillings");
    expect(body).toMatchObject({version: 3, document_id: "template", source_sha256: "source-hash", fields: saved.fields, idempotency_key: expect.any(String)});
    expect(body).not.toHaveProperty("approved");
    vi.mocked(workspaceApi).mockResolvedValue({...catalog, version: 4, fillings: [saved]});
    view.rerender(<NoticeFormWorkspace {...p} ws={updated}/>);
    await waitFor(() => expect(screen.getByRole("link", {name: "작성된 첨부 양식 다운로드 (HWPX)"})).toHaveAttribute("href", "/api/v2/notices/FORM/form-fillings/template/download"));
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue(saved.fields[0].value);
    expect(screen.getByLabelText("자료에서 발췌한 근거")).toHaveValue(saved.fields[0].value);
    expect(p.ws.inputs.documents[0].confirmed).toBe(false);
    expect(screen.getByText(/미작성 1개/)).toBeInTheDocument();
  });
  it("keeps per-field text and citations when switching fields or unsupported documents", async () => {
    render(<NoticeFormWorkspace {...props()}/>); await loaded(); companyReference();
    fireEvent.click(screen.getByRole("button", {name: /2\. 유지보수 계획/}));
    fireEvent.change(screen.getByLabelText("양식 항목 작성 내용"), {target: {value: "계획 초안"}});
    fireEvent.change(screen.getByLabelText("작성할 첨부 양식"), {target: {value: "pdf"}});
    expect(screen.getByText("PDF 원본은 직접 작성 대상이 아닙니다.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("작성할 첨부 양식"), {target: {value: "template"}});
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue("전력전자 기술 지원을 제공합니다.");
    expect(screen.getByLabelText("자료에서 발췌한 근거")).toHaveValue("전력전자 기술 지원을 제공합니다.");
    fireEvent.click(screen.getByRole("button", {name: /2\. 유지보수 계획/}));
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue("계획 초안");
  });
  it("preserves edits and requires source review after an input version changes", async () => {
    const p = props(); const view = render(<NoticeFormWorkspace {...p}/>); await loaded(); companyReference();
    vi.mocked(workspaceApi).mockResolvedValue({...catalog, version: 4});
    view.rerender(<NoticeFormWorkspace {...p} ws={{...p.ws, version: 4}}/>);
    await waitFor(() => expect(screen.getByRole("button", {name: "최신 자료를 확인하고 작성 이어가기"})).toBeEnabled());
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue("전력전자 기술 지원을 제공합니다.");
    expect(screen.getByRole("button", {name: "양식 초안 저장"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button", {name: "최신 자료를 확인하고 작성 이어가기"}));
    expect(screen.getByRole("button", {name: "양식 초안 저장"})).toBeEnabled();
    expect(workspaceApi).toHaveBeenCalledTimes(2);
  });
  it("blocks overwrite after the original form changes and preserves local text", async () => {
    const p = props(); const view = render(<NoticeFormWorkspace {...p}/>); await loaded(); companyReference();
    vi.mocked(workspaceApi).mockResolvedValue({...catalog, version: 4, documents: [{...catalog.documents[0], sha256: "changed-hash"}]});
    view.rerender(<NoticeFormWorkspace {...p} ws={{...p.ws, version: 4}}/>);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("원본 양식이나 저장본이 변경"));
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue("전력전자 기술 지원을 제공합니다.");
    expect(screen.getByRole("button", {name: "양식 초안 저장"})).toBeDisabled();
    expect(screen.queryByRole("button", {name: "최신 자료를 확인하고 작성 이어가기"})).not.toBeInTheDocument();
  });
  it("does not silently reuse an old saved filling against a different original", async () => {
    const p = props();
    const old = {document_id: "template", source_sha256: "old-hash", input_version: 2, review_status: "pending", fields: [{field_id: "slot1", value: "이전 양식 작성 내용"}]};
    vi.mocked(workspaceApi).mockResolvedValue({...catalog, fillings: [old]});
    render(<NoticeFormWorkspace {...p} ws={{...p.ws, inputs: {...p.ws.inputs, form_fillings: [old]}}}/>);
    await loaded();
    expect(screen.getByRole("alert")).toHaveTextContent("원본 양식이나 저장본이 변경");
    expect(screen.queryByRole("link", {name: "작성된 첨부 양식 다운로드 (HWPX)"})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "현재 입력 버리고 최신 저장본 불러오기"}));
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue("");
    expect(screen.getByRole("button", {name: "양식 초안 저장"})).toBeEnabled();
  });
  it("keeps disappeared attachments' unsaved text available to copy", async () => {
    const p = props(); const view = render(<NoticeFormWorkspace {...p}/>); await loaded(); companyReference();
    vi.mocked(workspaceApi).mockResolvedValue({...catalog, version: 4, documents: []});
    view.rerender(<NoticeFormWorkspace {...p} ws={{...p.ws, version: 4}}/>);
    await waitFor(() => expect((screen.getByLabelText("보관된 양식 작성 내용 1") as HTMLTextAreaElement).value).toContain("전력전자 기술 지원을 제공합니다."));
    expect(screen.queryByRole("button", {name: "양식 초안 저장"})).not.toBeInTheDocument();
  });
  it("validates missing and unsafe sources and keeps the same idempotency key for a failed retry", async () => {
    render(<NoticeFormWorkspace {...props()}/>); await loaded();
    fireEvent.change(screen.getByLabelText("양식 항목 작성 내용"), {target: {value: "작성 내용"}});
    fireEvent.click(screen.getByRole("button", {name: "양식 초안 저장"}));
    expect(screen.getByRole("status")).toHaveTextContent("출처를 연결하세요");
    fireEvent.change(screen.getByLabelText("참고자료 종류"), {target: {value: "web"}});
    fireEvent.change(screen.getByLabelText("자료 제목"), {target: {value: "노션 조사"}});
    fireEvent.change(screen.getByLabelText("노션·웹 주소"), {target: {value: "javascript:alert(1)"}});
    fireEvent.change(screen.getByLabelText("자료에서 발췌한 근거"), {target: {value: "작성 내용"}});
    fireEvent.click(screen.getByRole("button", {name: "양식 초안 저장"}));
    expect(screen.getByRole("status")).toHaveTextContent("http(s)");
    expect(workspaceApi).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("노션·웹 주소"), {target: {value: "https://www.notion.so/research"}});
    vi.mocked(workspaceApi).mockRejectedValue(new Error("연결을 확인하세요."));
    fireEvent.click(screen.getByRole("button", {name: "양식 초안 저장"}));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("연결을 확인하세요"));
    await waitFor(() => expect(screen.getByRole("button", {name: "양식 초안 저장"})).toBeEnabled());
    fireEvent.click(screen.getByRole("button", {name: "양식 초안 저장"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledTimes(3));
    expect(vi.mocked(workspaceApi).mock.calls[1][1]).toEqual(vi.mocked(workspaceApi).mock.calls[2][1]);
    expect(screen.getByLabelText("양식 항목 작성 내용")).toHaveValue("작성 내용");
  });
});
