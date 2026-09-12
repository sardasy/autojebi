"use client";

import {FormEvent, useEffect, useId, useRef, useState} from "react";
import {ChevronDown, ChevronRight, Database, FilePlus, Pencil, RefreshCw, Save, Search, X} from "lucide-react";

export interface SpecificationEvidenceSelection {
  document_id: string;
  quote: string;
  input_version: number;
}

export interface SpecificationWorkbenchProps {
  noticeNo: string;
  version: number;
  onChanged: () => void | Promise<void>;
  onChooseEvidence?: (evidence: SpecificationEvidenceSelection) => void;
}

type Detail = string | number | boolean | null | Detail[] | {[key: string]: Detail};
export interface SpecificationPayload {
  target: string;
  property: string;
  kind: "numeric" | "identifier" | "text";
  operator: "eq" | "lt" | "le" | "gt" | "ge" | "range" | "unknown";
  value: string | null;
  lower: string | null;
  upper: string | null;
  lower_inclusive?: boolean;
  upper_inclusive?: boolean;
  uncertainty?: string | null;
  tolerance?: string | null;
  unit: string;
  identifier: string;
  conditions: string;
  mandatory: boolean;
  raw: string;
  source: {
    document_id: string;
    document_sha256: string;
    text_sha256: string;
    start: number;
    end: number;
    quote: string;
    locator: string;
  };
}
export interface SpecificationItem {
  id: string;
  revision: number;
  etag: string;
  requirement_id: string | null;
  payload: SpecificationPayload;
  validation: {status: "valid" | "needs_review"; codes: string[]};
}
interface SpecificationList {
  items: SpecificationItem[];
  input_version: number;
  spec_compliance: Detail;
  unresolved_spec_count: number;
  source_complete: boolean;
  enabled: boolean;
  index_state?: {
    active_generation: string | null;
    latest_generation: string | null;
    status: string | null;
    input_version: number | null;
    current: boolean;
  } | null;
}
interface SearchItem {
  id: string;
  document_id: string;
  quote: string;
  locator: Detail;
  rrf: number;
  ranks: {lexical?: number; graph?: number; dense?: number};
  compliance: "meets" | "does_not_meet" | "unassessed";
  reason: string;
}
interface SearchResults {
  groups: {verified: SearchItem[]; references: SearchItem[]; conflicts: SearchItem[]};
  degraded: boolean;
  reasons: string[];
  generation: string | null;
}
interface EditState {
  item: SpecificationItem;
  payload: SpecificationPayload;
  version: number;
  note: string;
  conflicted: boolean;
  comparisonFailed: boolean;
  latest: SpecificationItem | null;
}
const field = "block w-full min-w-0 rounded border border-gray-300 bg-white p-2 text-sm";
const button = "inline-flex items-center justify-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-40";
const scalarFields = [
  ["target", "대상"], ["property", "속성"], ["value", "값"], ["lower", "하한"],
  ["upper", "상한"], ["unit", "단위"], ["identifier", "식별자"],
] as const;
const kinds: Record<string, string> = {numeric: "수치", identifier: "식별자", text: "문자"};
const operators: Record<string, string> = {eq: "같음 (=)", ge: "이상 (>=)", le: "이하 (<=)", gt: "초과 (>)", lt: "미만 (<)", range: "범위", unknown: "미확인"};
const complianceLabels: Record<string, string> = {meets: "충족", does_not_meet: "미충족", unassessed: "미평가", needs_review: "검토 필요"};
const groups = {verified: "검증된 근거", references: "참고자료 · 증빙 아님", conflicts: "상충 자료"};
const indexStates: Record<string, string> = {building: "생성 중", ready: "준비됨", failed: "실패", retired: "사용 종료", missing: "없음", absent: "없음", not_indexed: "미생성"};

function describe(value: Detail | undefined): string {
  if (value === null || value === undefined || value === "") return "미지정";
  if (typeof value === "boolean") return value ? "예" : "아니요";
  if (Array.isArray(value)) return value.length ? value.map(describe).join(" · ") : "없음";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${describe(item)}`).join(" · ") || "없음";
  return String(value);
}

function PayloadSummary({payload}: {payload: SpecificationPayload}) {
  return <dl className="grid grid-cols-[minmax(0,5rem)_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm [overflow-wrap:anywhere]">
    {scalarFields.map(([key, label]) => <div key={key} className="contents"><dt className="text-gray-500">{label}</dt><dd className="whitespace-pre-wrap">{describe(payload[key])}</dd></div>)}
    <dt>종류</dt><dd>{kinds[payload.kind] || payload.kind}</dd>
    <dt>비교</dt><dd>{operators[payload.operator || ""] || describe(payload.operator)}</dd>
    <dt>조건</dt><dd>{describe(payload.conditions)}</dd>
    {payload.operator === "range" && <><dt>경계 포함</dt><dd>하한 {payload.lower_inclusive === false ? "제외" : "포함"} · 상한 {payload.upper_inclusive === false ? "제외" : "포함"}</dd></>}
    {payload.uncertainty != null && <><dt>측정 불확도</dt><dd>{payload.uncertainty}</dd></>}
    {payload.tolerance != null && <><dt>요구 허용오차</dt><dd>{payload.tolerance}</dd></>}
    <dt>필수</dt><dd>{payload.mandatory ? "필수" : "선택"}</dd>
    <dt>원문</dt><dd className="whitespace-pre-wrap">{payload.raw}</dd>
  </dl>;
}

function Source({source}: {source: SpecificationPayload["source"]}) {
  return <details className="mt-2 text-sm [overflow-wrap:anywhere]">
    <summary className="cursor-pointer">출처 · {source.document_id}</summary>
    <blockquote className="my-2 border-l-2 pl-3 whitespace-pre-wrap">{source.quote}</blockquote>
    <p>위치: {describe(source.locator)} · 문자 {source.start}–{source.end}</p>
    <p>문서 SHA256: {source.document_sha256}</p><p>본문 SHA256: {source.text_sha256}</p>
  </details>;
}

async function readList(response: Response): Promise<SpecificationList> {
  if (!response.ok) throw new Error("list unavailable");
  const data: SpecificationList = await response.json();
  if (typeof data.enabled !== "boolean" || !Array.isArray(data.items)) throw new Error("invalid list");
  return data;
}

export default function SpecificationWorkbench(props: SpecificationWorkbenchProps) {
  return <Workbench key={props.noticeNo} {...props}/>;
}

function Workbench({noticeNo, version, onChanged, onChooseEvidence}: SpecificationWorkbenchProps) {
  const prefix = `/api/v2/notices/${encodeURIComponent(noticeNo)}`;
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState<SpecificationList | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [edit, setEdit] = useState<EditState | null>(null);
  const [query, setQuery] = useState("");
  const [requirement, setRequirement] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [resultsVersion, setResultsVersion] = useState<number | null>(null);
  const [pickedResult, setPickedResult] = useState<string | null>(null);
  const generation = useRef(0);
  const stale = data?.input_version !== version;

  useEffect(() => {
    generation.current++;
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setResults(null);
    fetch(`${prefix}/specifications`, {cache: "no-store", signal: controller.signal})
      .then(readList)
      .then(result => {if (!controller.signal.aborted) {setData(result); setError("");}})
      .catch(() => {if (!controller.signal.aborted) {setData(null); setError("사양 목록을 불러오지 못했습니다. 다시 조회하세요.");}})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [open, prefix, version, reload]);

  async function getItem(id: string) {
    const response = await fetch(`${prefix}/specifications/${encodeURIComponent(id)}`, {cache: "no-store"});
    if (!response.ok) throw new Error("item unavailable");
    const item: SpecificationItem = await response.json();
    return {...item, etag: response.headers.get("ETag") || item.etag};
  }

  async function startEdit(item: SpecificationItem) {
    setBusy(true); setError(""); setMessage("사양 조회 중");
    try {
      const current = await getItem(item.id);
      if (!current.etag) throw new Error("missing ETag");
      setEdit({item: current, payload: current.payload, version, note: "", conflicted: false, comparisonFailed: false, latest: null});
      setMessage("");
    } catch {setError("사양을 불러오지 못했습니다. 다시 조회하세요."); setMessage("");}
    finally {setBusy(false);}
  }

  async function notifyChanged(success: string) {
    setMessage(success);
    try {await onChanged();}
    catch {setError("요청은 처리됐지만 공고 상태 갱신에 실패했습니다. 최신 상태를 조회하세요.");}
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!edit || busy || edit.conflicted || stale || edit.version !== version || !edit.note.trim()) return;
    setBusy(true); setError(""); setMessage("사양 저장 중");
    try {
      const response = await fetch(`${prefix}/specifications/${encodeURIComponent(edit.item.id)}`, {
        method: "PUT", headers: {"Content-Type": "application/json", "If-Match": edit.item.etag},
        body: JSON.stringify({version: edit.version, payload: edit.payload, note: edit.note}),
      });
      if (response.status === 412 || response.status === 409) {
        setEdit(current => current ? {...current, conflicted: true} : current);
        setMessage("");
        try {
          const latest = await getItem(edit.item.id);
          setEdit(current => current ? {...current, latest} : current);
        } catch {setEdit(current => current ? {...current, comparisonFailed: true} : current);}
        return;
      }
      const updated = await readList(response);
      setData(updated); setEdit(null); setResults(null);
      await notifyChanged("담당자 수정 저장 완료 · 자동 검증 결과이며 승인이 아닙니다.");
    } catch {setMessage(""); setError("사양을 저장하지 못했습니다. 입력 내용은 유지했습니다.");}
    finally {setBusy(false);}
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || busy || loading || stale || !data?.enabled) return;
    const requestGeneration = generation.current;
    setBusy(true); setError(""); setMessage("근거 검색 중"); setResults(null); setPickedResult(null);
    try {
      const response = await fetch(`${prefix}/spec-search`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({...(requirement ? {requirement_id: requirement} : {}), query, limit: 5}),
      });
      if (!response.ok) throw new Error("search unavailable");
      const result: SearchResults = await response.json();
      if (requestGeneration !== generation.current) {setMessage(""); return;}
      if (!result.groups || !Object.keys(groups).every(key => Array.isArray(result.groups[key as keyof typeof groups]))) throw new Error("invalid results");
      setResults(result); setResultsVersion(version); setSearchedQuery(query); setMessage("검색 완료 · 자동 평가");
    } catch {setError("근거를 검색하지 못했습니다. 다시 검색하세요."); setMessage("");}
    finally {setBusy(false);}
  }

  async function index() {
    if (busy || stale || !data?.enabled) return;
    setBusy(true); setError(""); setMessage("색인 작업 접수 중");
    try {
      const response = await fetch(`${prefix}/jobs`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kind: "spec_index", input_version: data.input_version, idempotency_key: crypto.randomUUID()}),
      });
      if (!response.ok) throw new Error("index unavailable");
      await notifyChanged("색인 작업 접수 완료 · 완료 여부는 작업 상태에서 확인할 수 있습니다.");
    } catch {setError("색인 작업을 접수하지 못했습니다. 작업 상태를 확인하세요."); setMessage("");}
    finally {setBusy(false);}
  }

  const setPayload = (payload: SpecificationPayload) => setEdit(current => current ? {...current, payload} : current);
  return <section aria-label="사양 검토 작업대" className="min-w-0 border-y bg-white py-3 space-y-3">
    <button type="button" className={button} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
      {open ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}사양 검토·검색
    </button>
    <div id={panelId} hidden={!open} className="space-y-4 min-w-0">
      {open && <>
        <div role="status" aria-label="사양 작업 결과" className="text-sm text-gray-600">{loading ? "사양 불러오는 중" : message}</div>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="button" className={button} title="사양 새로고침" aria-label="사양 새로고침" disabled={busy || loading} onClick={() => setReload(value => value + 1)}><RefreshCw size={16}/></button>
        {data?.enabled === false && <p className="text-sm text-amber-800">사양 검토 기능이 활성화되지 않았습니다.</p>}
        {data?.enabled && <>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3 text-sm">
            <div><p>입력 버전 {data.input_version} · 미해결 사양 {data.unresolved_spec_count}개</p>
              <p>사양 충족 상태: {typeof data.spec_compliance === "string" ? complianceLabels[data.spec_compliance] || data.spec_compliance : describe(data.spec_compliance)} · 원문 {data.source_complete ? "확보 완료" : "확보 미완료"}</p>
              <p className="text-gray-500">담당자 검토와 승인: 별도 확인</p></div>
            <button type="button" className={button} disabled={busy || loading || stale} onClick={() => void index()}><Database size={16}/>사양 색인 생성</button>
          </div>
          {data.index_state && <div role="status" aria-label="사양 색인 상태" className="text-sm space-y-1 [overflow-wrap:anywhere]">
            <p>색인 상태: {indexStates[data.index_state.status || ""] || data.index_state.status || "미확인"} · {data.index_state.current ? "현재 입력과 일치" : "현재 입력용 색인 미확인"}</p>
            <p>색인 입력 버전: {data.index_state.input_version ?? "없음"}</p>
            <p>활성 세대: {data.index_state.active_generation || "없음"}</p>
            <p>최신 세대: {data.index_state.latest_generation || "없음"}</p>
          </div>}
          {(stale || (edit && edit.version !== version)) && <p role="alert" className="text-sm text-amber-800">입력 버전이 변경되었습니다. 작성 중인 내용은 유지되며 저장 전 최신 사양을 다시 열어야 합니다.</p>}
          {!data.items.length && <p className="text-sm">등록된 사양이 없습니다.</p>}
          <div className="divide-y">{data.items.map(item => <article key={item.id} className="py-3 min-w-0" aria-label={`${item.payload.target} ${item.payload.property}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2"><h3 className="font-medium text-sm break-words">{item.payload.target} · {item.payload.property} · 개정 {item.revision}</h3>
              <button type="button" className={button} aria-label={`${item.payload.target} ${item.payload.property} 수정`} title="사양 수정" disabled={busy || loading || stale || !!edit} onClick={() => void startEdit(item)}><Pencil size={16}/></button></div>
            <p className={`text-sm mb-2 ${item.validation.status === "valid" ? "text-green-800" : "text-amber-800"}`}>자동 검증: {item.validation.status === "valid" ? "유효" : "검토 필요"}{item.validation.codes.length > 0 && ` · ${item.validation.codes.join(", ")}`}</p>
            <PayloadSummary payload={item.payload}/><Source source={item.payload.source}/>
          </article>)}</div>
          {edit && <section aria-label="담당자 사양 수정" className="border-y py-4 space-y-3">
            <h3 className="text-base font-semibold">담당자 사양 수정 · 개정 {edit.item.revision}</h3>
            {edit.conflicted && <p role="alert" className="text-sm text-red-700">{edit.comparisonFailed ? "저장 충돌: 입력 내용은 유지했지만 최신 사양 조회에 실패했습니다." : "저장 충돌: 입력 내용은 유지했습니다. 최신 사양과 비교가 필요합니다. 자동 재저장하지 않습니다."}</p>}
            <div className={edit.latest ? "grid gap-6 lg:grid-cols-2 min-w-0" : "min-w-0"}>
              <form onSubmit={save} className="space-y-3 min-w-0">
                <fieldset disabled={busy} className="space-y-3 min-w-0"><legend className="text-sm font-medium mb-2">작성 중인 내용</legend>
                  <div className="grid gap-3 sm:grid-cols-2">{scalarFields.map(([key, label]) => <label key={key} className="text-sm min-w-0">{label}<input className={field} required={key === "target" || key === "property"} value={edit.payload[key] ?? ""} onChange={e => setPayload({...edit.payload, [key]: e.target.value === "" && (key === "value" || key === "lower" || key === "upper") ? null : e.target.value})}/></label>)}</div>
                  <div className="grid gap-3 sm:grid-cols-2">{([['kind', '종류', kinds], ['operator', '비교 연산자', operators]] as const).map(([key, label, options]) => <label key={key} className="text-sm min-w-0">{label}<select className={field} value={edit.payload[key] || ""} onChange={e => setPayload({...edit.payload, [key]: e.target.value || null})}>
                    {edit.payload[key] && !options[edit.payload[key]!] && <option value={edit.payload[key]!}>{edit.payload[key]}</option>}
                    {Object.entries(options).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
                  </select></label>)}</div>
                  {edit.payload.operator === "range" && <div className="flex flex-wrap gap-3">{([['lower_inclusive', '하한 포함'], ['upper_inclusive', '상한 포함']] as const).map(([key, label]) => <label key={key} className="text-sm"><input type="checkbox" checked={edit.payload[key] !== false} onChange={e => setPayload({...edit.payload, [key]: e.target.checked})}/> {label}</label>)}</div>}
                  <label className="block text-sm">요구 허용오차<input className={field} maxLength={100} value={edit.payload.tolerance ?? ""} onChange={e => setPayload({...edit.payload, tolerance: e.target.value || null})}/></label>
                  <label className="block text-sm">측정 불확도<input className={field} maxLength={100} value={edit.payload.uncertainty ?? ""} onChange={e => setPayload({...edit.payload, uncertainty: e.target.value || null})}/></label>
                  <label className="block text-sm">조건<textarea className={field} rows={2} maxLength={1000} value={edit.payload.conditions} onChange={e => setPayload({...edit.payload, conditions: e.target.value})}/></label>
                  <label className="block text-sm"><input type="checkbox" checked={edit.payload.mandatory} onChange={e => setPayload({...edit.payload, mandatory: e.target.checked})}/> 필수 사양</label>
                  <label className="block text-sm">원문 표현<textarea required maxLength={12000} className={field} rows={3} value={edit.payload.raw} onChange={e => setPayload({...edit.payload, raw: e.target.value})}/></label>
                  <label className="block text-sm">변경 사유<textarea required maxLength={2000} className={field} rows={2} value={edit.note} onChange={e => setEdit({...edit, note: e.target.value})}/></label>
                </fieldset>
                <Source source={edit.payload.source}/>
                <div className="flex flex-wrap gap-2"><button type="submit" className={button} disabled={busy || loading || stale || edit.conflicted || edit.version !== version || !edit.note.trim()}><Save size={16}/>사양 수정 저장</button>
                  <button type="button" className={button} disabled={busy} onClick={() => setEdit(null)}><X size={16}/>수정 취소</button></div>
              </form>
              {edit.latest && <aside aria-label="최신 사양 비교" className="min-w-0 border-l-2 border-amber-500 pl-3 space-y-2">
                <h4 className="text-sm font-semibold">최신 서버 사양 · 개정 {edit.latest.revision}</h4>
                <p className="text-sm">자동 검증: {edit.latest.validation.status === "valid" ? "유효" : "검토 필요"} · {edit.latest.validation.codes.join(", ")}</p>
                <PayloadSummary payload={edit.latest.payload}/><Source source={edit.latest.payload.source}/>
              </aside>}
            </div>
          </section>}
          <form onSubmit={search} className="flex flex-wrap gap-3 items-end border-t pt-4">
            <label className="text-sm min-w-0 flex-1 basis-48">근거 검색어<input required className={field} value={query} onChange={e => setQuery(e.target.value)}/></label>
            <label className="text-sm min-w-0 flex-1 basis-48">요구사항<select className={field} value={requirement} onChange={e => setRequirement(e.target.value)}><option value="">전체</option>{Array.from(new Set(data.items.map(item => item.requirement_id).filter((id): id is string => !!id))).map(id => <option key={id} value={id}>{id}</option>)}</select></label>
            <button type="submit" className={button} aria-label="사양 근거 검색" title="검색" disabled={busy || loading || stale || !query.trim()}><Search size={16}/></button>
          </form>
          {results && <section aria-label="사양 검색 결과" className="space-y-4 text-sm min-w-0">
            <p className="break-words">검색어: {searchedQuery} · 색인 세대: {results.generation || "없음"}</p>
            {results.degraded && <p role="status" className="text-amber-800">일부 검색 경로 사용 불가 · 제한된 검색 결과</p>}
            {results.reasons.length > 0 && <ul className="text-amber-800 break-words">{results.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>}
            {(Object.entries(groups) as [keyof typeof groups, string][]).map(([key, label]) => <section key={key} aria-label={label} className="border-t pt-3 min-w-0">
              <h3 className="font-semibold">{label} · {results.groups[key].length}건</h3>
              {!results.groups[key].length && <p className="text-gray-500 mt-2">검색 결과가 없습니다.</p>}
              <ul className="divide-y">{results.groups[key].map(item => <li key={item.id} className="py-3 space-y-1 [overflow-wrap:anywhere]">
                <p>{item.document_id} · {describe(item.locator)}</p><blockquote className="whitespace-pre-wrap border-l-2 pl-3">{item.quote}</blockquote>
                <p>자동 평가: {complianceLabels[item.compliance]} · {item.reason}</p>
                <p className="text-gray-500">결합 점수 {item.rrf} · 키워드 순위 {item.ranks.lexical ?? "없음"} · 관계 순위 {item.ranks.graph ?? "없음"} · 의미 순위 {item.ranks.dense ?? "없음"}</p>
                {key !== "conflicts" && onChooseEvidence && <button type="button" className={button} aria-pressed={pickedResult === `${key}:${item.id}`} disabled={busy || loading || stale || resultsVersion !== version} onClick={() => {
                  onChooseEvidence({document_id: item.document_id, quote: item.quote, input_version: resultsVersion!});
                  setPickedResult(`${key}:${item.id}`);
                }}><FilePlus size={16}/>작성 자료로 선택</button>}
              </li>)}</ul>
            </section>)}
          </section>}
        </>}
      </>}
    </div>
  </section>;
}
