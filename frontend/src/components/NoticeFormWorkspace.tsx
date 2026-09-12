"use client";

import {useEffect, useRef, useState} from "react";
import {Download, FileText, RefreshCw, Save} from "lucide-react";
import {SourceDocument, Workspace, workspaceApi} from "@/lib/workspace";

type Reference = {document_id: string; quote: string};
type WebReference = {title: string; url: string; quote: string};
type FieldValue = {field_id: string; value: string; reference?: Reference; web_reference?: WebReference};
type Filling = {document_id: string; source_sha256: string; fields: FieldValue[]; input_version: number; review_status: string};
type FormField = {id: string; label: string; context: string; original: string; location: string};
type FormDocument = {document_id: string; name: string; sha256: string; supported: boolean; reason?: string; fields: FormField[]};
type Catalog = {version: number; documents: FormDocument[]; fillings?: Filling[]};
type Draft = {documentId: string; sourceHash: string; version: number; fields: FieldValue[]; dirty: boolean; baseline: string};
const input = "block w-full min-w-0 rounded border border-gray-300 bg-white p-2 text-sm";
const button = "inline-flex items-center justify-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-40";
const usable = (d: SourceDocument) => !d.asset_issue && !d.company_asset?.stale && (d.role === "company_reference" || ((d.role === "company_evidence" || d.role === "product_evidence") && d.confirmed));
const fillings = (ws: Workspace) => (ws.inputs as Workspace["inputs"] & {form_fillings?: Filling[]}).form_fillings || [];
const fingerprint = (f?: Filling) => f ? JSON.stringify({source_sha256: f.source_sha256, fields: f.fields}) : "";
function fromSaved(document: FormDocument, version: number, saved?: Filling): Draft {
  return {documentId: document.document_id, sourceHash: saved?.source_sha256 || document.sha256, version, dirty: false, baseline: fingerprint(saved),
    fields: document.fields.map(field => saved?.fields.find(value => value.field_id === field.id) || {field_id: field.id, value: ""})};
}
function safeUrl(value: string) {
  try {const url = new URL(value); return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password;} catch {return false;}
}

export default function NoticeFormWorkspace({ws, prefix, busy, onSaved}: {
  ws: Workspace; prefix: string; busy: boolean; onSaved: (ws: Workspace) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [selectedField, setSelectedField] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [sectionId, setSectionId] = useState("");
  const request = useRef<{payload: string; key: string} | null>(null);
  const current = useRef(ws);
  current.current = ws;
  useEffect(() => {
    let stopped = false;
    setLoading(true);
    workspaceApi<Catalog>(`${prefix}/form-fields`).then(result => {
      if (stopped) return;
      if (!Array.isArray(result.documents)) throw new Error("첨부 양식 목록을 읽지 못했습니다.");
      setCatalog(result);
      setCatalogError("");
      setDrafts(existing => {
        const next = result.documents.map(document => {
          const local = existing.find(draft => draft.documentId === document.document_id);
          const saved = result.fillings?.find(item => item.document_id === document.document_id) || fillings(current.current).find(item => item.document_id === document.document_id);
          return local?.dirty ? local : fromSaved(document, result.version, saved);
        });
        return [...next, ...existing.filter(draft => draft.dirty && !next.some(item => item.documentId === draft.documentId))];
      });
      setSelectedDocument(id => result.documents.some(document => document.document_id === id) ? id : result.documents.find(document => document.supported)?.document_id || result.documents[0]?.document_id || "");
    }).catch(error => {if (!stopped) setCatalogError((error as Error).message);})
      .finally(() => {if (!stopped) setLoading(false);});
    return () => {stopped = true;};
  }, [prefix, ws.version, refresh]);
  useEffect(() => {
    if (!drafts.some(draft => draft.dirty)) return;
    const warn = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue = "";};
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [drafts]);
  const document = catalog?.documents.find(item => item.document_id === selectedDocument);
  const draft = drafts.find(item => item.documentId === selectedDocument);
  const saved = fillings(ws).find(item => item.document_id === selectedDocument) || catalog?.fillings?.find(item => item.document_id === selectedDocument);
  const field = document?.fields.find(item => item.id === selectedField) || document?.fields[0];
  const value = draft?.fields.find(item => item.field_id === field?.id);
  const references = ws.inputs.documents.filter(usable);
  const reference = references.find(item => item.id === value?.reference?.document_id);
  const disabled = busy || saving || loading;
  const conflicted = !!draft && (draft.sourceHash !== document?.sha256 || draft.baseline !== fingerprint(saved));
  const stale = !!draft && (draft.version !== ws.version || catalog?.version !== ws.version);
  const filled = draft?.fields.filter(item => item.value.trim()).length || 0;
  const canDownload = !!saved && saved.source_sha256 === document?.sha256 && !draft?.dirty && !stale && !ws.source_changed;
  const sections = ws.inputs.proposal_sections?.filter(item => item.text.trim()) || [];
  function edit(patch: Partial<FieldValue>) {
    if (!draft || !field || disabled) return;
    setDrafts(all => all.map(item => item.documentId === draft.documentId ? {...item, dirty: true, fields: item.fields.map(entry => entry.field_id === field.id ? {...entry, ...patch} : entry)} : item));
    setMessage("");
  }
  function validation(fields: FieldValue[]) {
    for (const entry of fields) {
      const label = document?.fields.find(item => item.id === entry.field_id)?.label || "작성 항목";
      if (entry.value.trim() && !entry.reference && !entry.web_reference) return `${label}: 작성 내용의 회사 자료 또는 노션·웹 출처를 연결하세요.`;
      if (entry.reference) {
        const source = references.find(item => item.id === entry.reference?.document_id);
        if (!source || !entry.reference.quote.trim() || !source.text.includes(entry.reference.quote)) return `${label}: 현재 회사 자료에 있는 발췌문을 그대로 입력하세요.`;
      }
      if (entry.web_reference && (!entry.web_reference.title.trim() || !entry.web_reference.quote.trim() || !safeUrl(entry.web_reference.url))) return `${label}: 노션·웹 자료의 제목, http(s) 주소, 발췌문을 확인하세요.`;
    }
    return "";
  }
  async function save() {
    if (!document || !draft || disabled || conflicted || stale || ws.source_changed) return;
    const error = validation(draft.fields);
    if (error) {setFailed(true); setMessage(error); return;}
    const body = {version: ws.version, document_id: document.document_id, source_sha256: document.sha256, fields: draft.fields.map(entry => ({field_id: entry.field_id, value: entry.value, ...(entry.reference ? {reference: {document_id: entry.reference.document_id, quote: entry.reference.quote}} : {}), ...(entry.web_reference ? {web_reference: {title: entry.web_reference.title, url: entry.web_reference.url, quote: entry.web_reference.quote}} : {})})), note: "공고 첨부 양식 항목별 초안 저장 · 내용 및 배치 검토 대기"};
    const payload = JSON.stringify(body);
    if (request.current?.payload !== payload) request.current = {payload, key: crypto.randomUUID()};
    setSaving(true); setFailed(false); setMessage("양식 초안 저장 중");
    try {
      const updated = await workspaceApi<Workspace>(`${prefix}/form-fillings`, {...body, idempotency_key: request.current!.key});
      const result = fillings(updated).find(item => item.document_id === document.document_id);
      if (!result) throw new Error("저장 응답에 양식 초안이 없습니다. 입력을 유지했습니다. 최신 상태를 확인하세요.");
      setDrafts(all => all.map(item => item.documentId === document.document_id ? fromSaved(document, updated.version, result) : item));
      setCatalog(old => old ? {...old, version: updated.version, fillings: [...(old.fillings || []).filter(item => item.document_id !== document.document_id), result]} : old);
      request.current = null; onSaved(updated); setMessage("첨부 양식 초안 저장 완료 · 미작성 항목과 문서 배치를 확인하세요.");
    } catch (error) {setFailed(true); setMessage((error as Error).message);}
    finally {setSaving(false);}
  }
  function acknowledgeVersion() {
    if (!draft || conflicted || catalog?.version !== ws.version || ws.source_changed) return;
    const error = validation(draft.fields);
    if (error) {setFailed(true); setMessage(error); return;}
    setDrafts(all => all.map(item => item.documentId === draft.documentId ? {...item, version: ws.version} : item));
    setMessage("현재 자료 기준으로 작성 이어가기 · 저장 전 내용을 확인하세요."); setFailed(false);
  }
  return <section aria-label="공고 첨부 양식 작성" className="min-w-0 space-y-4 rounded border bg-white p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="flex items-center gap-2 font-semibold"><FileText size={18}/>공고 첨부 양식 작성</h2><button className={button} disabled={busy || saving || loading} onClick={() => setRefresh(count => count + 1)}><RefreshCw size={15}/>양식 목록 새로고침</button></div>
    <p className="text-sm text-gray-600">공고에 첨부된 양식의 항목을 회사 자료와 노션 자료를 참고해 작성합니다. 저장한 내용은 해당 HWPX 양식에 채워 다운로드합니다.</p>
    {loading && <p role="status" className="text-sm">첨부 양식 항목을 불러오는 중입니다.</p>}
    {!loading && !catalog?.documents.length && <p className="text-sm">작성할 첨부 양식이 없습니다. 공고 원문 파일을 먼저 가져오세요.</p>}
    {drafts.filter(item => item.dirty && !catalog?.documents.some(source => source.document_id === item.documentId)).map((item, index) => <details key={item.documentId} className="space-y-2 rounded bg-amber-50 p-3 text-sm"><summary>목록에서 사라진 양식의 작성 내용 {index + 1} · 보관됨</summary><p>이 양식은 현재 첨부 목록에 없어 저장할 수 없습니다. 아래 작성 내용을 복사해 보관하세요.</p><textarea aria-label={`보관된 양식 작성 내용 ${index + 1}`} className={`${input} min-h-40`} readOnly value={item.fields.map((entry, fieldIndex) => `항목 ${fieldIndex + 1}\n${entry.value}\n${entry.reference?.quote || entry.web_reference?.quote || ""}`).join("\n\n")}/></details>)}
    {!!catalog?.documents.length && <label className="block text-sm">작성할 첨부 양식<select className={input} value={selectedDocument} disabled={busy || saving} onChange={event => {setSelectedDocument(event.target.value); setSelectedField(""); setSectionId(""); setMessage("");}}>{catalog.documents.map(item => <option key={item.document_id} value={item.document_id}>{item.name}{!item.supported ? " · 직접 확인 필요" : ""}</option>)}</select></label>}
    {document && !document.supported && <p className="rounded bg-amber-50 p-3 text-sm text-amber-900">{document.reason || "이 파일은 항목별 자동 작성이 지원되지 않습니다. 원본 양식을 직접 확인하세요."}</p>}
    {document && <a className="inline-block text-sm underline" href={`/api/v2${prefix}/documents/${encodeURIComponent(document.document_id)}/download`}>첨부 원본 다운로드</a>}
    {document?.supported && draft && <>
      <p className="text-sm">입력된 항목 {filled} / {document.fields.length}개 · 미작성 {document.fields.length - filled}개{draft.dirty ? " · 저장하지 않은 변경" : ""}</p>
      <p className="text-xs text-amber-800">빈 항목은 결과물에서 확인 필요로 표시합니다. 참고자료 연결은 자격증빙 승인이나 내용 확인을 뜻하지 않습니다. 다운로드 후 표·쪽 나눔·서명란을 검토하세요.</p>
      {(conflicted || stale || ws.source_changed) && <div role="alert" className="space-y-2 rounded bg-amber-50 p-3 text-sm text-amber-900"><p>{conflicted ? "원본 양식이나 저장본이 변경됐습니다. 입력한 내용은 유지했습니다. 복사해 보관한 뒤 최신 저장본과 비교하세요." : "자료가 변경되어 저장을 잠시 막았습니다. 입력한 내용을 현재 자료와 다시 대조하세요."}</p>{!conflicted && !ws.source_changed && <button className={button} disabled={disabled || catalog?.version !== ws.version} onClick={acknowledgeVersion}>최신 자료를 확인하고 작성 이어가기</button>}{conflicted && <button className={button} disabled={disabled} onClick={() => {const latest = fromSaved(document, catalog!.version, saved); if (saved && saved.source_sha256 !== document.sha256) {latest.sourceHash = document.sha256; latest.fields = document.fields.map(item => ({field_id: item.id, value: ""})); latest.dirty = true;} setDrafts(all => all.map(item => item.documentId === document.document_id ? latest : item)); setMessage("최신 양식과 저장본을 불러왔습니다. 원본이 변경된 항목은 다시 작성하세요.");}}>현재 입력 버리고 최신 저장본 불러오기</button>}</div>}
      {!!field && !!value && <div className="grid items-start gap-5 lg:grid-cols-[190px_minmax(0,1fr)_minmax(240px,0.8fr)]">
        <nav aria-label="양식 작성 항목" className="max-h-[620px] overflow-y-auto space-y-1 border-b pb-3 lg:border-b-0 lg:border-r lg:pr-3">{document.fields.map((item, index) => <button key={item.id} className={`block w-full rounded p-2 text-left text-sm ${field.id === item.id ? "bg-red-50 text-red-900" : "hover:bg-gray-50"}`} aria-pressed={field.id === item.id} disabled={busy || saving} onClick={() => {setSelectedField(item.id); setSectionId(""); setMessage("");}}><span>{index + 1}. {item.label}</span><span className="block text-xs text-gray-500">{draft.fields.find(entry => entry.field_id === item.id)?.value.trim() ? "내용 입력됨 · 검토 필요" : "미작성"}</span></button>)}</nav>
        <div className="min-w-0 space-y-3"><h3 className="font-semibold break-words">{field.label}</h3><details open className="text-sm"><summary>원본 양식의 안내와 주변 내용</summary><p className="whitespace-pre-wrap break-words py-2 text-gray-600">{field.context || "주변 안내문이 없습니다. 첨부 원본을 확인하세요."}</p>{field.original && <blockquote className="border-l-2 pl-3 whitespace-pre-wrap break-words">{field.original}</blockquote>}</details><label className="block text-sm">이 항목에 넣을 내용<textarea aria-label="양식 항목 작성 내용" className={`${input} min-h-[270px] leading-7`} value={value.value} disabled={disabled} onChange={event => edit({value: event.target.value})}/></label>
          {!!sections.length && <details className="space-y-2 text-sm"><summary>기존 작성 본문 가져오기</summary><label className="block">참고할 작성 본문<select className={input} value={sectionId} disabled={disabled} onChange={event => setSectionId(event.target.value)}><option value="">본문 선택</option>{sections.map((item, index) => <option key={item.id} value={item.id}>{item.title || `작성 본문 ${index + 1}`}</option>)}</select></label><button className={button} disabled={disabled || !sectionId} onClick={() => {const section = sections.find(item => item.id === sectionId); if (section) {edit({value: section.text, reference: undefined, web_reference: undefined}); setFailed(false); setMessage("본문을 넣었습니다. 이 항목을 뒷받침하는 출처를 연결하세요.");}}}>선택한 본문을 이 항목에 넣기</button></details>}
        </div>
        <aside aria-label="양식 항목 참고자료" className="min-w-0 space-y-3 border-t pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0"><h3 className="font-semibold text-sm">이 항목의 출처</h3><label className="block text-sm">참고자료 종류<select className={input} disabled={disabled} value={value.reference ? "company" : value.web_reference ? "web" : "none"} onChange={event => edit({reference: event.target.value === "company" ? {document_id: "", quote: ""} : undefined, web_reference: event.target.value === "web" ? {title: "", url: "", quote: ""} : undefined})}><option value="none">출처 선택</option><option value="company">등록된 회사 자료</option><option value="web">노션·웹 자료</option></select></label>
          {value.reference && <><label className="block text-sm">참고할 회사 자료<select className={input} disabled={disabled} value={value.reference.document_id} onChange={event => edit({reference: {document_id: event.target.value, quote: ""}})}><option value="">자료 선택</option>{references.map(item => <option key={item.id} value={item.id}>{item.name}{item.role === "company_reference" ? " · 참고용" : ""}</option>)}</select></label>{!references.length && <p className="text-sm text-gray-500">회사 폴더 자료를 아래 참고자료 등록 영역에서 추가하세요.</p>}{reference && <details className="text-sm"><summary>선택한 자료 본문 보기</summary><pre className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words py-2 font-sans">{reference.text}</pre></details>}<label className="block text-sm">자료에서 발췌한 근거<textarea className={`${input} min-h-32`} disabled={disabled} value={value.reference.quote} onChange={event => edit({reference: {...value.reference!, quote: event.target.value}})}/></label></>}
          {value.web_reference && <><p className="text-xs text-gray-500">노션 페이지 주소와 실제 확인한 내용을 넣으세요. 주소만으로 페이지 내용을 자동으로 가져오지는 않습니다.</p><label className="block text-sm">자료 제목<input className={input} disabled={disabled} value={value.web_reference.title} onChange={event => edit({web_reference: {...value.web_reference!, title: event.target.value}})}/></label><label className="block text-sm">노션·웹 주소<input className={input} disabled={disabled} type="url" value={value.web_reference.url} onChange={event => edit({web_reference: {...value.web_reference!, url: event.target.value}})}/></label><label className="block text-sm">자료에서 발췌한 근거<textarea className={`${input} min-h-32`} disabled={disabled} value={value.web_reference.quote} onChange={event => edit({web_reference: {...value.web_reference!, quote: event.target.value}})}/></label></>}
          {(value.reference || value.web_reference) && <button className={button} disabled={disabled || !(value.reference?.quote || value.web_reference?.quote)?.trim()} onClick={() => edit({value: value.reference?.quote || value.web_reference?.quote || ""})}>발췌문을 이 항목에 넣기</button>}
        </aside>
      </div>}
      <div className="flex flex-wrap items-center gap-3"><button className={`${button} border-red-700 bg-red-700 text-white`} disabled={disabled || !draft.dirty || conflicted || stale || ws.source_changed} onClick={() => void save()}><Save size={16}/>{saving ? "저장 중" : "양식 초안 저장"}</button>{canDownload && <a className={button} href={`/api/v2${prefix}/form-fillings/${encodeURIComponent(document.document_id)}/download`}><Download size={16}/>작성된 첨부 양식 다운로드 (HWPX)</a>}</div>
    </>}
    {catalogError && <p role="status" className="text-sm break-words text-red-700">{catalogError}</p>}
    {message && <p role="status" className={`text-sm break-words ${failed ? "text-red-700" : "text-green-800"}`}>{message}</p>}
  </section>;
}
