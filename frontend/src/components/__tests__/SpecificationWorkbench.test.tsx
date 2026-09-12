import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {NextRequest} from "next/server";
import SpecificationWorkbench, {SpecificationItem} from "../SpecificationWorkbench";
import {GET, PUT} from "@/app/api/v2/[...path]/route";

const item: SpecificationItem = {
  id: "spec 1", revision: 2, etag: '"revision-2"', requirement_id: "req-1",
  payload: {
    target: "전원", property: "전압", kind: "numeric", operator: "range",
    value: "0.00100", lower: "-0.00001", upper: "1000000000000000000.01",
    unit: "mV", identifier: "PART-001", conditions: "25 °C", mandatory: true,
    raw: "전압 원문", source: {document_id: "doc-1", document_sha256: "doc-hash",
      text_sha256: "text-hash", start: 10, end: 19, quote: "정확한 출처 인용", locator: "2쪽"},
  },
  validation: {status: "needs_review", codes: ["unit_mismatch"]},
};
const listing = {items: [item], input_version: 4, spec_compliance: "unassessed", unresolved_spec_count: 1, source_complete: false, enabled: true};
const fetchMock = vi.fn<typeof fetch>();
const changed = vi.fn<() => Promise<void>>();
const reply = (body: unknown, status = 200, headers?: HeadersInit) => new Response(JSON.stringify(body), {status, headers});

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  changed.mockResolvedValue(undefined);
});
afterEach(() => {vi.unstubAllGlobals(); vi.unstubAllEnvs();});

async function open() {
  render(<SpecificationWorkbench noticeNo="TEST 한글" version={4} onChanged={changed}/>);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {name: "사양 검토·검색"}));
  await screen.findByRole("button", {name: "전원 전압 수정"});
}
async function edit() {
  await open();
  fireEvent.click(screen.getByRole("button", {name: "전원 전압 수정"}));
  await screen.findByRole("region", {name: "담당자 사양 수정"});
  fireEvent.change(screen.getByLabelText("값"), {target: {value: "123.450000"}});
  fireEvent.change(screen.getByLabelText("변경 사유"), {target: {value: "원문 확인 후 수정"}});
}
const mutations = () => fetchMock.mock.calls.filter(([, init]) => init?.method && init.method !== "GET");

it("loads only when expanded and displays exact values, source and automatic validation", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing));
  await open();
  expect(fetchMock.mock.calls[0][0]).toBe("/api/v2/notices/TEST%20%ED%95%9C%EA%B8%80/specifications");
  expect(screen.getByText("0.00100")).toBeInTheDocument();
  expect(screen.getByText("1000000000000000000.01")).toBeInTheDocument();
  expect(screen.getByText("mV")).toBeInTheDocument();
  expect(screen.getByText(/자동 검증: 검토 필요/)).toHaveTextContent("unit_mismatch");
  expect(screen.getByText("정확한 출처 인용")).toBeInTheDocument();
  expect(screen.getByText(/문서 SHA256/)).toHaveTextContent("doc-hash");
  expect(screen.queryByRole("button", {name: /승인/})).not.toBeInTheDocument();
  expect(mutations()).toHaveLength(0);
});

it("reports explicitly disabled features without search or indexing actions", async () => {
  fetchMock.mockResolvedValueOnce(reply({...listing, enabled: false, items: []}));
  render(<SpecificationWorkbench noticeNo="TEST" version={4} onChanged={changed}/>);
  fireEvent.click(screen.getByRole("button", {name: "사양 검토·검색"}));
  expect(await screen.findByText("사양 검토 기능이 활성화되지 않았습니다.")).toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "사양 색인 생성"})).not.toBeInTheDocument();
  expect(screen.queryByLabelText("근거 검색어")).not.toBeInTheDocument();
  expect(mutations()).toHaveLength(0);
});

it.each([
  {active_generation:"active-4",latest_generation:"active-4",status:"ready",input_version:4,current:true},
  {active_generation:"old-3",latest_generation:"building-4",status:"building",input_version:4,current:false},
  {active_generation:null,latest_generation:null,status:null,input_version:null,current:false},
])("shows optional index state without inferring document approval: $status",async index_state=>{
  fetchMock.mockResolvedValueOnce(reply({...listing,index_state}));
  await open();
  const status=screen.getByRole("status",{name:"사양 색인 상태"});
  expect(status).toHaveTextContent(index_state.current ? "현재 입력과 일치" : "현재 입력용 색인 미확인");
  expect(status).toHaveTextContent(`활성 세대: ${index_state.active_generation || "없음"}`);
  expect(status).toHaveTextContent(`최신 세대: ${index_state.latest_generation || "없음"}`);
  expect(status).toHaveTextContent(`색인 입력 버전: ${index_state.input_version ?? "없음"}`);
  expect(status).not.toHaveTextContent("승인");
  expect(mutations()).toHaveLength(0);
});

it("keeps older responses without index state compatible",async()=>{
  fetchMock.mockResolvedValueOnce(reply(listing));
  await open();
  expect(screen.queryByRole("status",{name:"사양 색인 상태"})).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"사양 색인 생성"})).toBeEnabled();
});

it("saves explicitly with the single-item ETag, exact decimal strings and intact provenance", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing))
    .mockResolvedValueOnce(reply(item, 200, {ETag: '"header-revision-2"'}))
    .mockResolvedValueOnce(reply({...listing, input_version: 5}));
  await edit();
  fireEvent.change(screen.getByLabelText("단위"), {target: {value: "V"}});
  expect(mutations()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", {name: "사양 수정 저장"}));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  const [url, init] = mutations()[0];
  expect(url).toBe("/api/v2/notices/TEST%20%ED%95%9C%EA%B8%80/specifications/spec%201");
  expect(init?.method).toBe("PUT");
  expect(init?.headers).toEqual({"Content-Type": "application/json", "If-Match": '"header-revision-2"'});
  expect(JSON.parse(init?.body as string)).toEqual({version: 4, payload: {...item.payload, value: "123.450000", unit: "V"}, note: "원문 확인 후 수정"});
  expect(screen.queryByRole("region", {name: "담당자 사양 수정"})).not.toBeInTheDocument();
  expect(screen.getByRole("status", {name: "사양 작업 결과"})).toHaveTextContent("승인이 아닙니다");
});

it.each([409, 412])("preserves edits on %s and fetches the latest comparison without retry or approval", async status => {
  const latest = {...item, revision: 3, etag: '"revision-3"', payload: {...item.payload, value: "999.000"}};
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item))
    .mockResolvedValueOnce(reply({}, status)).mockResolvedValueOnce(reply(latest));
  await edit();
  fireEvent.click(screen.getByRole("button", {name: "사양 수정 저장"}));
  const comparison = await screen.findByRole("complementary", {name: "최신 사양 비교"});
  expect(within(comparison).getByText("999.000")).toBeInTheDocument();
  expect(screen.getByLabelText("값")).toHaveValue("123.450000");
  expect(screen.getByLabelText("변경 사유")).toHaveValue("원문 확인 후 수정");
  expect(screen.getByRole("button", {name: "사양 수정 저장"})).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("자동 재저장하지 않습니다");
  expect(fetchMock).toHaveBeenCalledTimes(4);
  expect(mutations()).toHaveLength(1);
  expect(changed).not.toHaveBeenCalled();
});

it("edits range boundaries and preserves empty text fields as strings", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item)).mockResolvedValueOnce(reply(listing));
  await edit();
  fireEvent.click(screen.getByLabelText("하한 포함"));
  fireEvent.change(screen.getByLabelText("측정 불확도"), {target: {value: "0.00010"}});
  for (const label of ["조건", "식별자", "단위"]) fireEvent.change(screen.getByLabelText(label), {target: {value: ""}});
  fireEvent.click(screen.getByRole("button", {name: "사양 수정 저장"}));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  expect(JSON.parse(mutations()[0][1]?.body as string).payload).toMatchObject({
    kind: "numeric", operator: "range", lower_inclusive: false, lower: "-0.00001",
    upper: "1000000000000000000.01", uncertainty: "0.00010", conditions: "", identifier: "", unit: "",
  });
  expect(JSON.parse(mutations()[0][1]?.body as string).payload).not.toHaveProperty("tolerance");
});

it("edits explicit requirement tolerance as an exact decimal without setting measurement uncertainty", async () => {
  const raw="출력 전압 10 mV, 허용오차 ±0.00100 mV";
  const withTolerance:SpecificationItem={...item,payload:{...item.payload,operator:"eq",value:"10",lower:null,upper:null,
    tolerance:"0.00100",uncertainty:null,raw,source:{...item.payload.source,quote:raw,end:item.payload.source.start+raw.length}}};
  fetchMock.mockResolvedValueOnce(reply({...listing,items:[withTolerance]})).mockResolvedValueOnce(reply(withTolerance)).mockResolvedValueOnce(reply(listing));
  await edit();
  expect(screen.getByLabelText("요구 허용오차")).toHaveValue("0.00100");
  expect(screen.getByLabelText("측정 불확도")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("요구 허용오차"),{target:{value:"0.000200"}});
  fireEvent.click(screen.getByRole("button",{name:"사양 수정 저장"}));
  await waitFor(()=>expect(changed).toHaveBeenCalledTimes(1));
  expect(JSON.parse(mutations()[0][1]?.body as string).payload).toMatchObject({
    tolerance:"0.000200",uncertainty:null,raw,source:withTolerance.payload.source,
  });
});

it.each([undefined,null])("keeps legacy tolerance %s unchanged without inferring it from uncertainty", async tolerance=>{
  const original={...item,payload:{...item.payload,uncertainty:"0.00010",...(tolerance===null?{tolerance:null}:{})}};
  fetchMock.mockResolvedValueOnce(reply({...listing,items:[original]})).mockResolvedValueOnce(reply(original)).mockResolvedValueOnce(reply(listing));
  await edit();
  expect(screen.getByLabelText("요구 허용오차")).toHaveValue("");
  expect(screen.getByLabelText("측정 불확도")).toHaveValue("0.00010");
  fireEvent.click(screen.getByRole("button",{name:"사양 수정 저장"}));
  await waitFor(()=>expect(changed).toHaveBeenCalledTimes(1));
  const saved=JSON.parse(mutations()[0][1]?.body as string).payload;
  expect(saved.uncertainty).toBe("0.00010");
  if(tolerance===null)expect(saved.tolerance).toBeNull();
  else expect(saved).not.toHaveProperty("tolerance");
});

it("offers only backend-supported kinds and comparison operators", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item));
  await edit();
  expect(within(screen.getByLabelText("종류")).getAllByRole("option").map(option => (option as HTMLOptionElement).value)).toEqual(["numeric", "identifier", "text"]);
  expect(within(screen.getByLabelText("비교 연산자")).getAllByRole("option").map(option => (option as HTMLOptionElement).value)).toEqual(["eq", "ge", "le", "gt", "lt", "range", "unknown"]);
  expect(mutations()).toHaveLength(0);
});

it("retains edits when fetching a conflict comparison also fails", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item))
    .mockResolvedValueOnce(reply({}, 412)).mockRejectedValueOnce(new Error("private diagnostic"));
  await edit();
  fireEvent.click(screen.getByRole("button", {name: "사양 수정 저장"}));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("최신 사양 조회에 실패"));
  expect(screen.getByLabelText("값")).toHaveValue("123.450000");
  expect(mutations()).toHaveLength(1);
  expect(screen.queryByText(/private diagnostic/)).not.toBeInTheDocument();
});

it("keeps the conflict warning visible after a subsequent search", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item))
    .mockResolvedValueOnce(reply({}, 412)).mockResolvedValueOnce(reply({...item, revision: 3}))
    .mockResolvedValueOnce(reply({groups: {verified: [], references: [], conflicts: []}, degraded: false, reasons: [], generation: null}));
  await edit();
  fireEvent.click(screen.getByRole("button", {name: "사양 수정 저장"}));
  await screen.findByRole("complementary", {name: "최신 사양 비교"});
  await waitFor(() => expect(screen.getByRole("button", {name: "수정 취소"})).toBeEnabled());
  fireEvent.change(screen.getByLabelText("근거 검색어"), {target: {value: "전압"}});
  fireEvent.click(screen.getByRole("button", {name: "사양 근거 검색"}));
  await screen.findByRole("region", {name: "사양 검색 결과"});
  expect(screen.getByRole("alert")).toHaveTextContent("저장 충돌");
  expect(screen.getByLabelText("값")).toHaveValue("123.450000");
  expect(screen.getByRole("button", {name: "사양 수정 저장"})).toBeDisabled();
});

it("retains fields on ordinary save failure", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item)).mockResolvedValueOnce(reply({}, 500));
  await edit();
  fireEvent.click(screen.getByRole("button", {name: "사양 수정 저장"}));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("사양을 저장하지 못했습니다"));
  expect(screen.getByLabelText("값")).toHaveValue("123.450000");
  expect(changed).not.toHaveBeenCalled();
});

it("preserves unsaved input but blocks saving when the workspace version changes", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply(item)).mockResolvedValueOnce(reply({...listing, input_version: 5}));
  const view = render(<SpecificationWorkbench noticeNo="TEST" version={4} onChanged={changed}/>);
  fireEvent.click(screen.getByRole("button", {name: "사양 검토·검색"}));
  fireEvent.click(await screen.findByRole("button", {name: "전원 전압 수정"}));
  await screen.findByLabelText("값");
  fireEvent.change(screen.getByLabelText("값"), {target: {value: "42.000"}});
  view.rerender(<SpecificationWorkbench noticeNo="TEST" version={5} onChanged={changed}/>);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  expect(screen.getByLabelText("값")).toHaveValue("42.000");
  expect(screen.getByRole("button", {name: "사양 수정 저장"})).toBeDisabled();
  expect(mutations()).toHaveLength(0);
});

it("searches only on submit and separates verified, reference and conflicting sources", async () => {
  const result = {id: "hit", document_id: "catalog", quote: "검증 인용", locator: {page: 3}, rrf: 0.025, ranks: {lexical: 1, graph: 2}, compliance: "meets", reason: "수치 일치"};
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply({
    groups: {verified: [result], references: [{...result, id: "ref", quote: "참고 인용", compliance: "unassessed"}], conflicts: [{...result, id: "conflict", quote: "상충 인용", compliance: "does_not_meet"}]},
    degraded: true, reasons: ["dense_unavailable"], generation: "generation-7",
  }));
  await open();
  fireEvent.change(screen.getByLabelText("근거 검색어"), {target: {value: "전압 100 V"}});
  fireEvent.change(screen.getByLabelText("요구사항"), {target: {value: "req-1"}});
  expect(mutations()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", {name: "사양 근거 검색"}));
  const verified = await screen.findByRole("region", {name: "검증된 근거"});
  expect(within(verified).getByText("검증 인용")).toBeInTheDocument();
  expect(within(screen.getByRole("region", {name: "참고자료 · 증빙 아님"})).getByText("참고 인용")).toBeInTheDocument();
  expect(within(screen.getByRole("region", {name: "상충 자료"})).getByText("상충 인용")).toBeInTheDocument();
  expect(screen.getByText(/제한된 검색 결과/)).toBeInTheDocument();
  expect(screen.getByText("dense_unavailable")).toBeInTheDocument();
  expect(screen.getByText(/generation-7/)).toBeInTheDocument();
  expect(mutations()[0][0]).toMatch(/\/spec-search$/);
  expect(JSON.parse(mutations()[0][1]?.body as string)).toEqual({requirement_id: "req-1", query: "전압 100 V", limit: 5});
  expect(changed).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", {name: /승인/})).not.toBeInTheDocument();
});

it("shows empty result groups and omits an unselected requirement", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply({groups: {verified: [], references: [], conflicts: []}, degraded: false, reasons: [], generation: null}));
  await open();
  fireEvent.change(screen.getByLabelText("근거 검색어"), {target: {value: "ABC"}});
  fireEvent.click(screen.getByRole("button", {name: "사양 근거 검색"}));
  expect(await screen.findAllByText("검색 결과가 없습니다.")).toHaveLength(3);
  expect(JSON.parse(mutations()[0][1]?.body as string)).toEqual({query: "ABC", limit: 5});
});

it("offers explicit evidence selection for verified and reference hits, never conflicts", async () => {
  const choose=vi.fn();
  const hit={id:"hit",document_id:"evidence",quote:"정확한 근거 인용",locator:"3쪽",rrf:0.02,ranks:{lexical:1},compliance:"meets",reason:"수치 일치"};
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply({groups:{
    verified:[hit], references:[{...hit,id:"ref",document_id:"reference",compliance:"unassessed"}], conflicts:[{...hit,id:"conflict",compliance:"does_not_meet"}],
  },degraded:false,reasons:[],generation:"gen-1"}));
  render(<SpecificationWorkbench noticeNo="TEST" version={4} onChanged={changed} onChooseEvidence={choose}/>);
  fireEvent.click(screen.getByRole("button",{name:"사양 검토·검색"}));
  await screen.findByLabelText("근거 검색어");
  fireEvent.change(screen.getByLabelText("근거 검색어"),{target:{value:"전압"}});
  fireEvent.click(screen.getByRole("button",{name:"사양 근거 검색"}));
  const verified=await screen.findByRole("region",{name:"검증된 근거"});
  expect(choose).not.toHaveBeenCalled();
  fireEvent.click(within(verified).getByRole("button",{name:"작성 자료로 선택"}));
  expect(choose).toHaveBeenLastCalledWith({document_id:"evidence",quote:"정확한 근거 인용",input_version:4});
  expect(within(verified).getByRole("button",{name:"작성 자료로 선택"})).toHaveAttribute("aria-pressed","true");
  fireEvent.click(within(screen.getByRole("region",{name:"참고자료 · 증빙 아님"})).getByRole("button",{name:"작성 자료로 선택"}));
  expect(choose).toHaveBeenLastCalledWith({document_id:"reference",quote:"정확한 근거 인용",input_version:4});
  expect(within(screen.getByRole("region",{name:"상충 자료"})).queryByRole("button",{name:"작성 자료로 선택"})).not.toBeInTheDocument();
  expect(mutations()).toHaveLength(1);
  expect(changed).not.toHaveBeenCalled();
});

it("ignores a search response from the previous input version", async () => {
  let resolveSearch!: (response: Response) => void;
  fetchMock.mockResolvedValueOnce(reply(listing))
    .mockImplementationOnce(() => new Promise(resolve => {resolveSearch = resolve;}))
    .mockResolvedValueOnce(reply({...listing, input_version: 5}));
  const view = render(<SpecificationWorkbench noticeNo="TEST" version={4} onChanged={changed}/>);
  fireEvent.click(screen.getByRole("button", {name: "사양 검토·검색"}));
  await screen.findByLabelText("근거 검색어");
  fireEvent.change(screen.getByLabelText("근거 검색어"), {target: {value: "voltage"}});
  fireEvent.click(screen.getByRole("button", {name: "사양 근거 검색"}));
  view.rerender(<SpecificationWorkbench noticeNo="TEST" version={5} onChanged={changed}/>);
  await act(async () => resolveSearch(reply({groups: {verified: [], references: [], conflicts: []}, degraded: false, reasons: [], generation: "outdated"})));
  expect(screen.queryByRole("region", {name: "사양 검색 결과"})).not.toBeInTheDocument();
});

it("shows search failures and does not treat them as empty results", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply({}, 503));
  await open();
  fireEvent.change(screen.getByLabelText("근거 검색어"), {target: {value: "ABC"}});
  fireEvent.click(screen.getByRole("button", {name: "사양 근거 검색"}));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("근거를 검색하지 못했습니다"));
  expect(screen.queryByRole("region", {name: "사양 검색 결과"})).not.toBeInTheDocument();
  expect(mutations()).toHaveLength(1);
});

it("handles 202 Accepted for an explicit spec_index job using the current version", async () => {
  fetchMock.mockResolvedValueOnce(reply(listing)).mockResolvedValueOnce(reply({
    id: "job-1", notice_no: "TEST 한글", kind: "spec_index", input_version: 4,
    status: "queued", quality: null, parameters: {}, result: null, error: null,
    created_at: "2026-09-11T00:00:00Z", started_at: null, finished_at: null, execution_lane: "external",
  }, 202));
  await open();
  expect(mutations()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", {name: "사양 색인 생성"}));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  const [url, init] = mutations()[0];
  expect(url).toMatch(/\/jobs$/);
  expect(JSON.parse(init?.body as string)).toEqual({kind: "spec_index", input_version: 4, idempotency_key: expect.any(String)});
  expect(JSON.parse(init?.body as string).idempotency_key.length).toBeGreaterThan(20);
  expect(mutations()).toHaveLength(1);
});

it("exposes list failures accessibly and permits explicit refresh", async () => {
  fetchMock.mockRejectedValueOnce(new Error("secret")).mockResolvedValueOnce(reply(listing));
  render(<SpecificationWorkbench noticeNo="TEST" version={4} onChanged={changed}/>);
  fireEvent.click(screen.getByRole("button", {name: "사양 검토·검색"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("사양 목록을 불러오지 못했습니다");
  fireEvent.click(screen.getByRole("button", {name: "사양 새로고침"}));
  await screen.findByRole("button", {name: "전원 전압 수정"});
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

describe("specification proxy concurrency headers", () => {
  it("forwards If-Match and returns ETag with an unchanged conflict status", async () => {
    vi.stubEnv("FRONTEND_ORIGIN", "http://localhost:3000");
    fetchMock.mockResolvedValueOnce(reply({}, 412, {ETag: '"latest"'}));
    const request = new NextRequest("http://localhost:3000/api/v2/notices/TEST/specifications/spec", {method: "PUT", headers: {Origin: "http://localhost:3000", "Content-Type": "application/json", "If-Match": '"original"'}, body: "{}"});
    const response = await PUT(request, {params: Promise.resolve({path: ["notices", "TEST", "specifications", "spec"]})});
    expect(response.status).toBe(412);
    expect(response.headers.get("etag")).toBe('"latest"');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("if-match")).toBe('"original"');
  });

  it("returns the single-item ETag on GET", async () => {
    fetchMock.mockResolvedValueOnce(reply(item, 200, {ETag: '"single"'}));
    const response = await GET(new NextRequest("http://localhost:3000/api/v2/notices/TEST/specifications/spec"), {params: Promise.resolve({path: ["notices", "TEST", "specifications", "spec"]})});
    expect(response.headers.get("etag")).toBe('"single"');
  });
});
