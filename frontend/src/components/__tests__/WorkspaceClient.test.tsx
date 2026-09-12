import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceClient from "../WorkspaceClient";
import { SourceAttachment, SourceDocument, Workspace, workspaceApi } from "@/lib/workspace";

vi.mock("@/lib/workspace", async importOriginal => {
  const actual = await importOriginal<typeof import("@/lib/workspace")>();
  return {...actual, workspaceApi: vi.fn()};
});
const fixture: Workspace = {notice_no: "V2", version: 1, decision: "pending", ready: false, source_changed: false,
  inputs: {notice: {title: "실무 검토", org_name: "기관", close_date: null, base_price: null}, documents: [], requirements: [], checklist: [], source_reviewed: false, legacy_warning: true, company: {}},
  blockers: ["필수 서류 확인 필요"], next_action: "필수 서류 확인 필요", jobs: [], reviews: []};
Object.assign(fixture, {items: [{template_key: "bid_form", name: "입찰참가신청서"}, {template_key: "proposal", name: "제안서"}, {template_key: "proposal_layout_v1", name: "제안서 · 실무 서식"}]});
const sourceDocument: SourceDocument = {id: "manual", name: "수동등록자료.pdf", role: "notice_source", confirmed: true, text: "기존 확인 본문", text_origin: "manual", attachment_index: 1};
const sourceAttachments: SourceAttachment[] = [
  {index: 1, name: "공고문.pdf", url: "https://www.g2b.go.kr/file/1", document_ids: ["manual"], state: "ready"},
  {index: 2, name: "규격서.hwp", url: "https://g2b.go.kr/file/2", document_ids: ["second"], state: "ready"},
  {index: 3, name: "제안요청서.pdf", url: "http://www.g2b.go.kr/file/3", document_ids: ["third"], state: "unread"},
  {index: 4, name: "기술지원_가격산출내역.xls", url: "", document_ids: [], state: "missing"},
];

describe("WorkspaceClient", () => {
  beforeEach(() => {vi.mocked(workspaceApi).mockReset(); window.history.replaceState(null, "", "/");});
  it("shows partial archive extraction and OCR review without marking sources complete", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, inputs:{...fixture.inputs, documents:[{...sourceDocument,
      extraction:{complete:false, members:[{name:"drawing.dwg",sha256:"a".repeat(64),size:10,status:"unsupported",complete:false}],
        pages:[{page_no:2,method:"ocr",status:"extracted",review_required:true,confidence:91}]},
    }]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByText("추출 내역 · 일부 미확인")).toBeInTheDocument();
    expect(screen.getByText(/drawing.dwg · 미지원 형식/)).toBeInTheDocument();
    expect(screen.getByText(/2쪽 · OCR 본문 · 원문 대조 필요/)).toBeInTheDocument();
    expect(screen.getByText("본문 · 일부 확인 가능")).toBeInTheDocument();
  });
  it("guides an empty requirement list directly to source registration without creating a blocked job", async () => {
    vi.mocked(workspaceApi).mockResolvedValue(fixture);
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name:"4. 서류 확인"}));
    expect(screen.getByRole("button", {name:"누락 검사"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button", {name:"원문 기반 요구사항 등록"}));
    expect(screen.getByRole("tab", {name:"2. 공고 서류 검토"})).toHaveAttribute("aria-selected", "true");
    await waitFor(()=>expect(document.getElementById("source-requirement-entry")).toHaveAttribute("open"));
    expect(vi.mocked(workspaceApi).mock.calls.some(([path])=>path.endsWith("/jobs"))).toBe(false);
  });
  it("tracks the recovered job through completion in the result banner", async () => {
    const failed = {id: "old", kind: "excel", input_version: 1, status: "failed", quality: null,
      result: null, error: {code: "execution_failed", message: "생성 실패", next_action: "재생성"},
      created_at: "2026-09-10T00:00:00Z", finished_at: null};
    const completed = {...failed, id: "new", status: "succeeded", error: null};
    let recovered = false;
    vi.mocked(workspaceApi).mockImplementation(async path => {
      if (path.endsWith("/recover")) {recovered = true; return completed;}
      return {...fixture, jobs: recovered ? [completed, failed] : [failed]};
    });
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "실패 원인 확인 후 재생성"}});
    fireEvent.click(screen.getByRole("button", {name: "복구·재생성"}));
    await waitFor(() => expect(screen.getByRole("status", {name: "실행 결과"})).toHaveTextContent("Excel 생성 · 완료"));
  });
  it("records a template inspection request and exposes missing fields without artifact approval", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, jobs:[{
      id:"inspect", kind:"hwp_inspect", input_version:1, status:"succeeded", quality:"warning",
      result:{fields:["company_name"], required_missing:["proposal_body"], unmapped:["unused"], inspection_passed:false},
      error:null, created_at:"2026-09-08T00:00:00Z", finished_at:"2026-09-08T00:01:00Z",
    }]});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name:"4. 서류 확인"}));
    expect(screen.getByText(/실제 필드 1개 · 필드 보완 필요 · 미매핑 unused/)).toBeInTheDocument();
    expect(screen.queryByRole("button", {name:"초안 승인"})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name:"템플릿 필드 검사"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/jobs", expect.objectContaining({kind:"hwp_inspect", input_version:1, template_key:"bid_form"})));
  });
  it("offers the concrete missing attachment action instead of a no-op tab change", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: sourceAttachments});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name:"3. 비교·작성"}));
    fireEvent.click(within(screen.getByRole("region", {name:"지금 할 작업"})).getByRole("button", {name:"누락 첨부 가져오기"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/jobs", expect.objectContaining({kind:"fetch", input_version:1})));
  });
  it("offers one primary apply action and hides empty editing surfaces", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments:[{...sourceAttachments[0],state:"missing",document_ids:[]}], jobs:[{
      id:"downloaded", kind:"fetch", input_version:1,status:"succeeded",quality:null,error:null,created_at:"2026-09-11T00:00:00Z",finished_at:null,
      result:{documents:[{id:"new",role:"notice_source",attachment_index:1}]},
    }]});
    render(<WorkspaceClient noticeNo="V2"/>);
    const action = await screen.findByRole("region",{name:"지금 할 작업"});
    expect(within(action).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText("다운로드 완료 · 반영 대기")).toBeInTheDocument();
    expect(screen.queryByRole("region",{name:"공고 원문 미리보기"})).not.toBeInTheDocument();
    expect(screen.getByText(/원문·증빙 파일 관리/).closest("details")).not.toHaveAttribute("open");
    fireEvent.click(within(action).getByRole("button",{name:"다운로드한 첨부 반영"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/jobs/downloaded/apply",{version:1}));
    expect(vi.mocked(workspaceApi).mock.calls.some(([path]) => path.endsWith("/jobs"))).toBe(false);
  });
  it("disables the primary action while a job is queued without starting another job", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture,jobs:[{id:"waiting",kind:"fetch",input_version:1,status:"queued",quality:null,result:null,error:null,created_at:"2026-09-11T00:00:00Z",finished_at:null}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByRole("button",{name:"처리 중"})).toBeDisabled();
    expect(vi.mocked(workspaceApi).mock.calls.some(([path]) => path.endsWith("/jobs"))).toBe(false);
  });
  it("compares past writing with source and saves a versioned pending draft", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, writing_plan_current:true, inputs: {...fixture.inputs,
      writing_plan:{reviewed_at:"2026-09-11",reviewed_version:1,items:[{id:"proposal",title:"정성제안서",document_kind:"qualitative_proposal",action:"write",document_id:"source",quote:"3대 필요"}]},
      documents: [{...sourceDocument, id: "old", role: "company_reference", name: "지난 제안서.pdf", text: "이전 납품은 3대"}],
      requirements: [{id: "req", text: "3대 공급", document_id: "source", quote: "3대 필요", locator: "1페이지", category: "technical", mandatory: true, proposed_value: "", evidence_id: null, evidence_quote: "", evidence_locator: "", review_status: "pending"}],
    }});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "3. 비교·작성"}));
    expect(screen.getByText("3대 필요")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("참고할 회사 자료"), {target:{value:"old"}});
    expect(screen.getByLabelText("회사 참고자료 본문")).toHaveValue("이전 납품은 3대");
    expect(screen.queryByRole("button", {name: "증빙 확인"})).not.toBeInTheDocument();
    const save = screen.getByRole("button", {name: "서류 초안 저장"});
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("참고 발췌문"), {target: {value: "다른 문장"}});
    expect(screen.getByRole("button",{name:"발췌문 넣기"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("서류 작성 내용"), {target: {value: "3대를 공급합니다. [검증필요]"}});
    fireEvent.change(screen.getByLabelText("참고 발췌문"), {target: {value: "이전 납품은 3대"}});
    fireEvent.click(screen.getByRole("button",{name:"발췌문 넣기"}));
    fireEvent.click(save);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/document-drafts", expect.objectContaining({
      version: 1, draft_id:"proposal", references:[{document_id: "old", quote: "이전 납품은 3대"}],
      text: "3대를 공급합니다. [검증필요]\n\n[검증필요] 이전 납품은 3대",
    })));
  });
  it("shows only the document loop and preserves legacy warnings", async () => {
    vi.mocked(workspaceApi).mockResolvedValue(fixture);
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByText("실무 검토")).toBeInTheDocument();
    expect(screen.getByText(/기존 점수와 승인은/)).toBeInTheDocument();
    expect(screen.getByText("서류 확인 필요")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", {name: "참가 결정"})).not.toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("link", {name: "1. 공고 찾기"})).toHaveAttribute("href", "/workspace");
  });
  it("keeps blocked HWP visible without approval controls", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, jobs: [{id: "one", kind: "hwp", input_version: 1, status: "blocked", quality: null, result: null, error: {code: "required_missing", message: "사업자번호 누락", next_action: "회사 정보 확인"}, created_at: "2026-09-06T00:00:00Z", finished_at: null}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    expect((await screen.findAllByText(/사업자번호 누락/)).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", {name: "초안 승인"})).not.toBeInTheDocument();
  });
  it("supports keyboard tab movement and durable job requests", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, inputs:{...fixture.inputs, documents:[sourceDocument]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    const original = await screen.findByRole("tab", {name: "2. 공고 서류 검토"});
    fireEvent.keyDown(original, {key: "ArrowRight"});
    expect(screen.getByRole("tab", {name: "3. 비교·작성"})).toHaveAttribute("aria-selected", "true");
    fireEvent.click(original);
    fireEvent.click(screen.getByRole("button", {name: "요구사항 분석"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/jobs", expect.objectContaining({kind: "analyze", input_version: 1})));
  });
  it("requires source text rather than company reference text for analysis", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, inputs:{...fixture.inputs, documents:[{...sourceDocument, role:"company_reference"}]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByRole("button", {name:"요구사항 분석"})).toBeDisabled();
    expect(screen.getByRole("status", {name:"원문 준비 상태"})).toHaveTextContent("등록된 공고 원문이 없습니다");
  });
  it("offers explicit attachment application before extraction without auto-running jobs", async () => {
    const state: Workspace = {...fixture, jobs:[{id:"fetch", kind:"fetch", input_version:1, status:"succeeded", quality:null,
      result:{documents:[{id:"new", role:"notice_source"}]}, error:null, created_at:"2026-09-09T00:00:00Z", finished_at:null}]};
    vi.mocked(workspaceApi).mockResolvedValue(state);
    render(<WorkspaceClient noticeNo="V2"/>);
    const apply = await screen.findByRole("button", {name:"첨부 결과 반영"});
    expect(screen.getByRole("button", {name:"본문 추출"})).toBeDisabled();
    expect(screen.getByRole("button", {name:"요구사항 분석"})).toBeDisabled();
    fireEvent.click(apply);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/jobs/fetch/apply", {version:1}));
    expect(vi.mocked(workspaceApi).mock.calls.some(([path])=>path.endsWith("/jobs"))).toBe(false);
  });
  it("requires extraction result application before analysis", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, inputs:{...fixture.inputs, documents:[{...sourceDocument, text:"   "}]},
      jobs:[{id:"extract", kind:"extract", input_version:1, status:"succeeded", quality:null,
        result:{documents:[{id:"manual", text:"읽은 공고 본문", format:"pdf"}]}, error:null, created_at:"2026-09-09T00:00:00Z", finished_at:null}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("button", {name:"본문 결과 반영"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/jobs/extract/apply", {version:1}));
    expect(screen.getByRole("button", {name:"요구사항 분석"})).toBeDisabled();
  });
  it("does not offer obsolete or already-applied extraction results", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, inputs:{...fixture.inputs, documents:[sourceDocument]}, jobs:[
      {id:"old", kind:"extract", input_version:0, status:"succeeded", quality:null, result:{documents:[{id:"manual", text:"old"}]}, error:null, created_at:"2026-09-09T00:00:00Z", finished_at:null},
      {id:"same", kind:"extract", input_version:1, status:"succeeded", quality:null, result:{documents:[{id:"manual", text:sourceDocument.text}]}, error:null, created_at:"2026-09-09T00:00:00Z", finished_at:null},
    ]});
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByRole("button", {name:"요구사항 분석"})).toBeEnabled();
    expect(screen.queryByRole("button", {name:"본문 결과 반영"})).not.toBeInTheDocument();
  });
  it("shows missing mandatory proposal coverage separately from accepted requirements", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, proposal_coverage: {mandatory_count: 2, covered_count: 1, evidence_only_count: 0, missing_ids: ["B"]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    expect(screen.getByText(/제안서 필수 항목 2개 · 본문 대응 1개 · 별도 증빙 0개 · 미대응 1개/)).toBeInTheDocument();
  });
  it("sends the last review id when changing artifact review", async () => {
    const state: Workspace = {...fixture, jobs: [{id: "file", kind: "excel", input_version: 1, status: "succeeded", quality: "warning", result: {artifact: "output.xlsx"}, error: null, created_at: "2026-09-07T00:00:00Z", finished_at: null}], reviews: [{id: "last-review", job_id: "file", action: "approved", note: "Previous", input_version: 1, created_at: "2026-09-07T00:00:01Z"}]};
    vi.mocked(workspaceApi).mockResolvedValue(state);
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    expect(await screen.findByText("검토 상태: 승인")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "Changed after checking"}});
    fireEvent.click(screen.getByRole("button", {name: "반려"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/reviews", expect.objectContaining({expected_review_id: "last-review", action: "rejected"})));
  });
  it("requires worker confirmation for HWP recovery", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, jobs: [{id: "failed-hwp", kind: "hwp", input_version: 1, status: "failed", quality: null, result: null, error: {code: "interrupted", message: "확인 필요", next_action: "Worker 확인"}, created_at: "2026-09-07T00:00:00Z", finished_at: null}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    const button = await screen.findByRole("button", {name: "복구·재생성"});
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "Existing output checked"}});
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", {name: "Worker 종료·기존 파일 확인"}));
    fireEvent.click(button);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/jobs/failed-hwp/recover", expect.objectContaining({external_state_confirmed: true})));
  });
  it("excludes grading and SKU output from the document loop", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, jobs: [{id: "grade", kind: "grade", input_version: 1, status: "succeeded", quality: "warning", result: {
      axes: {spec: {score: null, state: "unassessed", reason: "담당자 판정 필요"}, qualification: {score: 0, state: "evaluated", reason: "필수 자격 미충족"}}, score_total: null, technical_coverage: 1,
      candidates: [{sku: {sku_id: "SKU-1", name: "Test product"}, similarity: .99, review_status: "pending"}],
    }, error: null, created_at: "2026-09-07T00:00:00Z", finished_at: null}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    await screen.findByText("실무 검토");
    for (const name of ["2. 공고 서류 검토", "3. 비교·작성", "4. 서류 확인"]) {
      fireEvent.click(screen.getByRole("tab", {name}));
      expect(screen.queryByText(/검색 유사도|담당자 판정 필요/)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", {name: "알림 미리보기"})).not.toBeInTheDocument();
    }
  });
  it("does not show saved-field verification as final submission approval", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, jobs: [{id: "hwp", kind: "hwp", input_version: 1, status: "succeeded", quality: "warning", result: {artifact: "draft.hwp", verified: true, required_missing: ["ceo"], remaining_placeholders: ["address"]}, error: null, created_at: "2026-09-07T00:00:00Z", finished_at: null}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    expect(await screen.findByText("저장값 재조회: 일치 확인 · 문서 배치 검토 필요")).toBeInTheDocument();
    expect(screen.getByText("필수 누락: ceo")).toBeInTheDocument();
    expect(screen.getByText("미입력 항목: address")).toBeInTheDocument();
    expect(screen.getByText("서류 확인 필요")).toBeInTheDocument();
  });
  it("sends price evidence as a versioned human input", async () => {
    vi.mocked(workspaceApi).mockResolvedValue(fixture);
    render(<WorkspaceClient noticeNo="V2"/>);
    fireEvent.click(await screen.findByRole("tab", {name: "4. 서류 확인"}));
    fireEvent.click(screen.getByText("제안 총액·견적 근거"));
    fireEvent.change(screen.getByLabelText("제안 총액 (원)"), {target: {value: "100000"}});
    fireEvent.change(screen.getByLabelText("견적 페이지·문단"), {target: {value: "p1"}});
    fireEvent.change(screen.getByLabelText("원화 총액 원문 인용"), {target: {value: "100,000원"}});
    fireEvent.change(screen.getByLabelText("담당자 확인 의견"), {target: {value: "총액 확인"}});
    fireEvent.submit(screen.getByRole("button", {name: "견적 근거 저장"}).closest("form")!);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/commercial", expect.objectContaining({version: 1, offer_price: 100000, quantity: 1, quote: "100,000원"})));
  });
  it("lists missing XLS alongside every official attachment without implying approval", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: sourceAttachments, inputs: {...fixture.inputs, documents: [sourceDocument]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    const table = await screen.findByRole("table", {name: "나라장터 첨부 목록"});
    for (const attachment of sourceAttachments) expect(within(table).getByText(attachment.name)).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    expect(within(within(table).getByRole("row", {name: /기술지원_가격산출내역.xls/})).getByText("파일 미확보")).toBeInTheDocument();
    expect(within(table).getByText("본문 미확인")).toBeInTheDocument();
    expect(within(table).getAllByText("본문 확보")).toHaveLength(2);
    expect(within(table).queryByText(/승인|확인됨/)).not.toBeInTheDocument();
    expect(screen.getByText("목록 4개 · 파일 연결 3개 · 본문 확보 2개")).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "원문 전체 대조 확인"})).toBeDisabled();
  });
  it.each(["missing", "unread"] as const)("blocks whole-source review for %s inventory despite prior confirmation", async state => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: [{...sourceAttachments[0], state}], inputs: {...fixture.inputs, source_reviewed: true, documents: [sourceDocument]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    const review = await screen.findByRole("button", {name: "원문 전체 대조 확인"});
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "대조 의견"}});
    expect(review).toBeDisabled();
    fireEvent.click(review);
    expect(workspaceApi).not.toHaveBeenCalledWith("/notices/V2/source-review", expect.anything());
  });
  it("enables human source review once all inventory text is ready without posting automatically", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: sourceAttachments.map(a => ({...a, state: "ready"}))});
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByRole("button", {name: "원문 전체 대조 확인"})).toBeEnabled();
    expect(workspaceApi).not.toHaveBeenCalledWith("/notices/V2/source-review", expect.anything());
  });
  it("links a manual source to a slot without a URL using a note and current version only", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, version: 7, source_attachments: sourceAttachments, inputs: {...fixture.inputs, documents: [sourceDocument]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    const select = await screen.findByRole("combobox", {name: "수동등록자료.pdf 나라장터 첨부 연결"});
    const save = screen.getByRole("button", {name: "수동등록자료.pdf 첨부 연결 저장"});
    expect(select).toHaveValue("1");
    fireEvent.change(select, {target: {value: "4"}});
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "   "}});
    fireEvent.submit(save.closest("form")!);
    expect(workspaceApi).not.toHaveBeenCalledWith("/notices/V2/documents/manual/source-link", expect.anything());
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "공식 첨부 4번과 수동 등록 파일 대조"}});
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/documents/manual/source-link", {version: 7, attachment_index: 4, note: "공식 첨부 4번과 수동 등록 파일 대조"}));
    expect(workspaceApi).not.toHaveBeenCalledWith("/notices/V2/documents/manual/review", expect.anything());
    expect(workspaceApi).not.toHaveBeenCalledWith("/notices/V2/source-review", expect.anything());
  });
  it("allows only listed integer attachment slots from 1 through 10", async () => {
    const invalid = [0, 11, 1.5].map(index => ({...sourceAttachments[0], index, name: `invalid-${index}`}));
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: [...sourceAttachments, ...invalid], inputs: {...fixture.inputs, documents: [{...sourceDocument, attachment_index: 11}]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    const select = await screen.findByRole("combobox", {name: "수동등록자료.pdf 나라장터 첨부 연결"});
    expect(within(select).getAllByRole("option").map(option => (option as HTMLOptionElement).value)).toEqual(["", "1", "2", "3", "4"]);
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "첨부 대조"}});
    const save = screen.getByRole("button", {name: "수동등록자료.pdf 첨부 연결 저장"});
    expect(save).toBeDisabled();
    fireEvent.submit(save.closest("form")!);
    expect(workspaceApi).not.toHaveBeenCalledWith("/notices/V2/documents/manual/source-link", expect.anything());
  });
  it.each([undefined, []])("keeps manual text editing and review compatible without an inventory (%j)", async source_attachments => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments, inputs: {...fixture.inputs, documents: [sourceDocument]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    expect(await screen.findByRole("button", {name: "원문 전체 대조 확인"})).toBeEnabled();
    expect(screen.queryByRole("table", {name: "나라장터 첨부 목록"})).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", {name: /나라장터 첨부 연결/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("본문 · 확인 가능"));
    const text = screen.getByLabelText("수동등록자료.pdf 본문");
    expect(text).toHaveValue("기존 확인 본문");
    fireEvent.change(text, {target: {value: "다시 대조한 본문"}});
    fireEvent.change(screen.getByLabelText("검토 의견"), {target: {value: "수동 대조"}});
    fireEvent.click(screen.getByRole("button", {name: "확인된 본문 저장"}));
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices/V2/documents/manual/text", {version: 1, text: "다시 대조한 본문", note: "수동 대조"}));
  });
  it.each(["company_evidence", "product_evidence"] as const)("does not offer official source linking for %s", async role => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: sourceAttachments, inputs: {...fixture.inputs, documents: [{...sourceDocument, role}]}});
    render(<WorkspaceClient noticeNo="V2"/>);
    await screen.findByRole("table", {name: "나라장터 첨부 목록"});
    expect(screen.queryByRole("combobox", {name: /나라장터 첨부 연결/})).not.toBeInTheDocument();
  });
  it.each([
    ["https://www.g2b.go.kr/file?index=4", true],
    ["http://g2b.go.kr/file", true],
    ["https://user:password@www.g2b.go.kr/file", false],
    ["https://www.g2b.go.kr.evil.invalid/file", false],
    ["https://evil.invalid/g2b.go.kr", false],
    ["javascript:alert(1)", false],
    ["//www.g2b.go.kr/file", false],
    ["ftp://www.g2b.go.kr/file", false],
    ["https://www.g2b.go.kr:8443/file", false],
    ["", false],
  ])("renders an official download link only for a safe URL: %s", async (url, allowed) => {
    vi.mocked(workspaceApi).mockResolvedValue({...fixture, source_attachments: [{...sourceAttachments[3], url: String(url)}]});
    render(<WorkspaceClient noticeNo="V2"/>);
    const table = await screen.findByRole("table", {name: "나라장터 첨부 목록"});
    expect(within(table).getByText("기술지원_가격산출내역.xls")).toBeInTheDocument();
    const link = within(table).queryByRole("link", {name: "기술지원_가격산출내역.xls 나라장터 원본 열기"});
    if (allowed) {
      expect(link).toHaveAttribute("href", url);
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    } else expect(link).not.toBeInTheDocument();
  });
});
