"use client";

import {useEffect, useRef, useState} from "react";
import {BookOpen, Download, ExternalLink, FileText, Plus, Save, Search, X} from "lucide-react";
import {DocumentKind, SourceDocument, WebWritingReference, Workspace, WritingReference, workspaceApi} from "@/lib/workspace";
import {buildNoticeBrief} from "@/lib/noticeBrief";

const input = "block w-full min-w-0 rounded border border-gray-300 bg-white p-2 text-sm";
const button = "inline-flex items-center justify-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-40";
const kinds: Record<DocumentKind, string> = {qualitative_proposal: "정성제안서", bid_document: "입찰서", other_document: "기타서류"};
type Section = NonNullable<Workspace["inputs"]["proposal_sections"]>[number];
export interface SelectedWritingEvidence {document_id: string; quote: string; key: string; input_version: number}
const usableReference = (document: SourceDocument) => document.role === "company_reference" ||
  ((document.role === "company_evidence" || document.role === "product_evidence") && document.confirmed && !document.asset_issue);
type Draft = {id: string; kind: DocumentKind; title: string; text: string; references: WritingReference[]; web: WebWritingReference[]; dirty: boolean; baseline: string};
const fingerprint = (s?: Section) => s ? JSON.stringify(s) : "";
function fromSection(s: Section): Draft {
  return {id:s.id, kind:s.document_kind!, title:s.title || "작성 서류", text:s.text, references:s.references || [], web:s.web_references || [], dirty:false, baseline:fingerprint(s)};
}
function initialDrafts(ws: Workspace): Draft[] {
  return (ws.inputs.writing_plan?.items || []).filter(item=>item.action === "write").map(item=>{
    const saved=ws.inputs.proposal_sections?.find(s=>s.id===item.id);
    return saved ? {...fromSection(saved),title:item.title,kind:item.document_kind} : {id:item.id,kind:item.document_kind,title:item.title,text:"",references:[],web:[],dirty:false,baseline:""};
  });
}
export function searchUrl(query: string, provider: "google" | "naver") {
  return `${provider === "google" ? "https://www.google.com/search?q=" : "https://search.naver.com/search.naver?query="}${encodeURIComponent(query.trim())}`;
}

export default function DocumentWritingWorkspace({ws, prefix, busy, onSaved, onRefresh, onReview, selectedEvidence}: {
  ws: Workspace; prefix: string; busy: boolean; onSaved: (ws:Workspace)=>void; onRefresh: ()=>Promise<boolean>; onReview?:()=>void;
  selectedEvidence?: SelectedWritingEvidence | null;
}) {
  const [drafts,setDrafts] = useState(()=>initialDrafts(ws));
  const [selected,setSelected] = useState(drafts[0]?.id || "");
  const [saving,setSaving] = useState(false);
  const [message,setMessage] = useState("");
  const [failed,setFailed] = useState(false);
  const [sourceTab,setSourceTab] = useState<"notice"|"company"|"web">("company");
  const [filter,setFilter] = useState("");
  const [referenceId,setReferenceId] = useState("");
  const [quote,setQuote] = useState("");
  const [quoteInputVersion,setQuoteInputVersion] = useState<number | null>(null);
  const handledEvidence = useRef<string | null>(null);
  const [query,setQuery] = useState("");
  const [provider,setProvider] = useState<"google"|"naver">("google");
  const [web,setWeb] = useState({title:"",url:"",quote:""});
  const requestRef = useRef<{payload:string; key:string} | null>(null);
  const draft = drafts.find(d=>d.id===selected)!;
  const target=ws.inputs.writing_plan?.items.find(item=>item.id===selected && item.action==="write");
  const saved = ws.inputs.proposal_sections?.find(s=>s.id===selected);
  const references = ws.inputs.documents.filter(usableReference);
  const reference = references.find(d=>d.id===referenceId);
  const brief = buildNoticeBrief(ws.inputs.documents);
  const disabled = busy || saving;
  const staleQuote = quoteInputVersion !== null && quoteInputVersion !== ws.version;
  useEffect(()=>{
    if (!selectedEvidence || handledEvidence.current === selectedEvidence.key || busy || saving) return;
    handledEvidence.current = selectedEvidence.key;
    const document = ws.inputs.documents.find(d=>d.id===selectedEvidence.document_id && usableReference(d));
    if (selectedEvidence.input_version !== ws.version || !document || !selectedEvidence.quote.trim() || !document.text.includes(selectedEvidence.quote)) {
      setFailed(true); setMessage("선택한 자료의 입력 버전·사용 가능 여부·원문 인용을 확인하세요. 작성 내용은 변경하지 않았습니다."); return;
    }
    setSourceTab("company"); setFilter(""); setReferenceId(document.id); setQuote(selectedEvidence.quote);
    setQuoteInputVersion(selectedEvidence.input_version);
    setFailed(false); setMessage("작성 참고자료 선택 완료 · 본문 반영 전");
  },[selectedEvidence, ws.version, ws.inputs.documents, busy, saving]);
  useEffect(()=>{
    setDrafts(current=>{
      return initialDrafts(ws).map(server=>current.find(d=>d.id===server.id && d.dirty) || server);
    });
    const targets=ws.inputs.writing_plan?.items.filter(i=>i.action==="write") || [];
    setSelected(id=>targets.some(i=>i.id===id)?id:targets[0]?.id || "");
  },[ws]);
  useEffect(()=>{
    if (!drafts.some(d=>d.dirty)) return;
    const warn = (e:BeforeUnloadEvent)=>{e.preventDefault(); e.returnValue="";};
    window.addEventListener("beforeunload",warn);
    return ()=>window.removeEventListener("beforeunload",warn);
  },[drafts]);
  function edit(patch:Partial<Draft>) {
    setDrafts(all=>all.map(d=>d.id===selected ? {...d,...patch,dirty:true} : d)); setMessage("");
  }
  function openReferenceFiles() {
    const section = document.getElementById("writing-reference-files") as HTMLDetailsElement | null;
    if (section) {section.open=true;section.scrollIntoView({block:"start"});section.querySelector("input")?.focus();}
  }
  async function save() {
    if (disabled) return;
    if (draft.baseline !== fingerprint(saved)) {
      setFailed(true); setMessage("다른 화면에서 이 서류가 수정됐습니다. 현재 입력을 복사해 보관한 뒤 최신 저장본과 비교하세요."); return;
    }
    const body = {draft_id:draft.id, document_kind:draft.kind,title:draft.title,text:draft.text,
      references:draft.references.map(r=>({document_id:r.document_id,quote:r.quote})),
      web_references:draft.web.map(r=>({title:r.title,url:r.url,quote:r.quote})),note:"문서별 작성 초안 저장 · 사람 검토 대기"};
    const payload = JSON.stringify(body);
    if (requestRef.current?.payload !== payload) requestRef.current={payload,key:crypto.randomUUID()};
    setSaving(true); setFailed(false); setMessage("초안 저장 중");
    try {
      const updated = await workspaceApi<Workspace>(`${prefix}/document-drafts`,{...body,version:ws.version,idempotency_key:requestRef.current!.key});
      const result = updated.inputs.proposal_sections!.find(s=>s.id===draft.id)!;
      setDrafts(all=>all.map(d=>d.id===draft.id ? fromSection(result) : d));
      onSaved(updated); requestRef.current=null; setMessage(`${draft.title} 저장 완료 · 검토 대기`);
    } catch(e) {setFailed(true); setMessage((e as Error).message);}
    finally {setSaving(false);}
  }
  function addCompanyQuote() {
    if (disabled || staleQuote || !reference || !quote.trim() || !reference.text.includes(quote) || draft.references.length >= 30) return;
    edit({references:[...draft.references,{document_id:reference.id,name:reference.name,quote}],
      text:`${draft.text}${draft.text ? "\n\n" : ""}[검증필요] ${quote}`}); setQuote("");
  }
  function addWebQuote() {
    try {
      const url = new URL(web.url);
      if (!["https:","http:"].includes(url.protocol) || url.username || url.password) throw new Error();
      if (!web.title.trim() || !web.quote.trim()) throw new Error();
      edit({web:[...draft.web,{...web,url:url.href,verified:false}], text:`${draft.text}${draft.text ? "\n\n" : ""}[검증필요] ${web.quote}`});
      setWeb({title:"",url:"",quote:""});
    } catch {setFailed(true); setMessage("웹 자료의 제목·http(s) 주소·발췌문을 확인하세요.");}
  }
  if(!ws.writing_plan_current || ws.source_changed || !draft || !target) return <section aria-label="문서별 비교 작성" className="py-4 space-y-3"><h2 className="font-semibold">공고에서 확인한 작성 항목</h2><p className="text-sm">{ws.writing_plan_current ? "확인한 목록에 직접 작성할 항목이 없습니다." : "공고 서류 검토에서 작성·첨부 대상을 먼저 확인하세요."}</p><button className={button} onClick={onReview}>공고 서류 검토로 이동</button>{!!ws.inputs.proposal_sections?.length && <p className="text-sm text-gray-500">기존 초안은 서류 확인에 보존되어 있습니다.</p>}</section>;
  return <section aria-label="문서별 비교 작성" className="space-y-4 min-w-0">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">공고에서 확인한 작성 항목</h2><button className={button} disabled={disabled} onClick={onReview}>작성 대상 검토·수정</button></div>
    <p className="text-xs text-gray-500">직접 작성 {drafts.length}개 · 발급·원본 첨부 {ws.inputs.writing_plan?.items.filter(i=>i.action==="attach").length}개 · 전자 제출 {ws.inputs.writing_plan?.items.filter(i=>i.action==="electronic").length}개</p>
    <div className="grid lg:grid-cols-[180px_minmax(0,1fr)_300px] gap-5 items-start">
      <label className="lg:hidden text-sm">작성 서류 선택<select className={input} value={selected} disabled={saving} onChange={e=>{setSelected(e.target.value);setMessage("");}}>{drafts.map(d=><option key={d.id} value={d.id}>{d.title || "새 서류"} · {d.dirty ? "저장 전" : d.baseline ? "저장됨" : "미작성"}</option>)}</select></label>
      <nav aria-label="작성 서류 목록" className="hidden lg:block min-w-0 space-y-4 border-r pr-3">
        {(Object.entries(kinds) as [DocumentKind,string][]).filter(([kind])=>drafts.some(d=>d.kind===kind)).map(([kind,label])=><div key={kind}><h3 className="text-xs font-semibold text-gray-500 mb-1">{label}</h3>{drafts.filter(d=>d.kind===kind).map(d=><button key={d.id} aria-pressed={selected===d.id} className={`flex w-full gap-2 text-left py-2 px-2 text-sm border-l-2 ${selected===d.id ? "border-red-700 bg-red-50" : "border-transparent"}`} disabled={saving} onClick={()=>{setSelected(d.id);setMessage("");}}><FileText size={16} className="shrink-0 mt-0.5"/><span className="min-w-0 break-words">{d.title || "새 서류"}<span className="block text-xs text-gray-500 mt-1">{d.dirty ? "저장 전" : d.baseline ? "저장됨" : "미작성"}</span></span></button>)}</div>)}
      </nav>
      <div className="min-w-0 space-y-3">
        <div><p className="text-xs text-gray-500">{kinds[draft.kind]}</p><h3 className="font-semibold break-words">{draft.title}</h3></div>
        <details open className="border-l-2 pl-3 text-sm"><summary>이 항목의 공고 요구 내용</summary><blockquote className="whitespace-pre-wrap break-words py-2">{target.quote}</blockquote><a className="underline text-xs" href={`/api/v2${prefix}/documents/${target.document_id}/download`}>근거 원문 다운로드</a></details>
        <div className="flex flex-wrap justify-between gap-2 items-center"><span className="text-xs text-amber-800">{draft.dirty ? "저장하지 않은 변경" : "검토용 초안"}</span>{!draft.text.trim() && <button className={button} disabled={disabled} onClick={()=>edit({text:`# ${draft.title}\n\n[검증필요]`})}><Plus size={16}/>항목 제목 넣기</button>}</div>
        <label className="block text-sm">작성 내용<textarea aria-label="서류 작성 내용" className={`${input} min-h-[420px] leading-7 resize-y`} value={draft.text} disabled={disabled} onChange={e=>edit({text:e.target.value})}/></label>
        {draft.kind === "bid_document" && <p className="text-xs text-amber-800">검토용 입찰서입니다. 나라장터 금액 입력·투찰은 실행하지 않습니다.</p>}
        {draft.kind === "other_document" && <p className="text-xs text-amber-800">사업자등록증·신용등급확인서 등 발급 서류는 직접 작성하지 않고 원본을 첨부해야 합니다.</p>}
        {!!(draft.references.length+draft.web.length) && <details className="text-sm"><summary>이 서류의 참고자료 {draft.references.length+draft.web.length}개 · 사실 확인 필요</summary><ul className="divide-y">{draft.references.map((r,i)=><li key={`r-${i}`} className="py-2 flex gap-2 justify-between min-w-0"><div className="min-w-0 break-words"><strong>{r.name}</strong><p className="whitespace-pre-wrap">{r.quote}</p></div><button disabled={disabled} className="self-start p-1" title="출처 연결 해제 (본문 유지)" aria-label={`${r.name} 출처 연결 해제`} onClick={()=>edit({references:draft.references.filter((_,j)=>j!==i)})}><X size={16}/></button></li>)}{draft.web.map((r,i)=><li key={`w-${i}`} className="py-2 flex gap-2 justify-between min-w-0"><div className="min-w-0 break-words"><a className="underline" href={r.url} target="_blank" rel="noreferrer">{r.title}</a><span className="text-amber-800"> · 검증필요</span><p className="whitespace-pre-wrap">{r.quote}</p></div><button disabled={disabled} className="self-start p-1" title="출처 연결 해제 (본문 유지)" aria-label={`${r.title} 출처 연결 해제`} onClick={()=>edit({web:draft.web.filter((_,j)=>j!==i)})}><X size={16}/></button></li>)}</ul></details>}
        <div className="flex flex-wrap gap-2 items-center"><button className={`${button} bg-red-700 text-white border-red-700`} disabled={disabled || ws.source_changed || !draft.text.trim() || !draft.title.trim() || !draft.dirty} onClick={()=>void save()}><Save size={16}/>{saving ? "저장 중" : "서류 초안 저장"}</button>{saved && !draft.dirty && <a className={button} href={`/api/v2${prefix}/document-drafts/${draft.id}/download`}><Download size={16}/>텍스트 초안 다운로드</a>}</div>
        {message && <p role="status" className={`text-sm break-words ${failed ? "text-red-700" : "text-green-800"}`}>{message}</p>}
        {failed && <button className={button} onClick={()=>void onRefresh()}>최신 저장 상태 확인</button>}
      </div>
      <aside aria-label="작성 참고자료" className="min-w-0 border-t lg:border-t-0 lg:border-l lg:pl-4 pt-3 lg:pt-0 space-y-3">
        <h3 className="font-semibold text-sm flex gap-2 items-center"><BookOpen size={16}/>참고자료</h3>
        <div className="flex border-b" role="group" aria-label="참고자료 종류">{([['notice','공고 원문'],['company','회사 자료'],['web','웹검색']] as const).map(([key,label])=><button key={key} aria-pressed={sourceTab===key} className={`flex-1 py-2 text-sm border-b-2 ${sourceTab===key ? "border-red-700 font-semibold" : "border-transparent"}`} onClick={()=>setSourceTab(key)}>{label}</button>)}</div>
        {sourceTab === "notice" && <div className="space-y-3 max-h-[650px] overflow-y-auto"><h4 className="text-sm font-semibold">공고 제출서류</h4>{brief.submissions.length ? brief.submissions.map((item,i)=><div key={i} className="text-sm border-b pb-2 break-words"><p>{item.text}</p><a className="text-xs underline text-gray-500" href={`/api/v2${prefix}/documents/${item.documentId}/download`}>{item.documentName}</a></div>) : <p className="text-sm text-gray-500">추출한 제출서류가 없습니다. 공고 원문을 확인하세요.</p>}</div>}
        {sourceTab === "company" && <div className="space-y-3">
          <label className="block text-sm">회사 자료 검색<input className={input} value={filter} onChange={e=>setFilter(e.target.value)}/></label>
          <label className="block text-sm">참고할 회사 자료<select className={input} value={referenceId} onChange={e=>{setReferenceId(e.target.value);setQuote("");setQuoteInputVersion(ws.version);}}><option value="">자료 선택</option>{references.filter(r=>`${r.name} ${r.text}`.toLowerCase().includes(filter.toLowerCase()) || r.id===referenceId).map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          {!references.length && <p className="text-sm text-gray-500">등록된 회사 자료가 없습니다.</p>}
          {reference && <>
            <label className="block text-sm">참고자료 본문<textarea aria-label="회사 참고자료 본문" readOnly className={`${input} h-48`} value={reference.text || "본문 추출 필요"} onSelect={e=>{const el=e.currentTarget;if(reference.text && el.selectionEnd>el.selectionStart){setQuote(el.value.slice(el.selectionStart,el.selectionEnd));setQuoteInputVersion(ws.version);}}}/></label>
            <label className="block text-sm">참고 발췌문<textarea className={`${input} h-24`} value={quote} onChange={e=>{setQuote(e.target.value);setQuoteInputVersion(ws.version);}}/></label>
            <button className={button} disabled={disabled || staleQuote || !quote.trim() || !reference.text.includes(quote) || draft.references.length>=30} onClick={addCompanyQuote}><Plus size={16}/>발췌문 넣기</button>
            {staleQuote && <p className="text-xs text-amber-800">발췌문 선택 이후 입력 버전이 변경되었습니다. 최신 자료에서 다시 선택하세요.</p>}
            {quote && !reference.text.includes(quote) && <p className="text-xs text-amber-800">원문에 없는 발췌문입니다.</p>}
          </>}
          <a href="#writing-reference-files" onClick={e=>{e.preventDefault();openReferenceFiles();}} className="inline-flex text-sm underline gap-1"><Plus size={16}/>회사 자료 등록·본문 확인</a>
        </div>}
        {sourceTab === "web" && <div className="space-y-3"><label className="block text-sm">검색어<input className={input} value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="block text-sm">검색 서비스<select className={input} value={provider} onChange={e=>setProvider(e.target.value as typeof provider)}><option value="google">Google</option><option value="naver">네이버</option></select></label><a className={`${button} ${!query.trim() ? "pointer-events-none opacity-40" : ""}`} aria-disabled={!query.trim()} tabIndex={query.trim()?0:-1} href={searchUrl(query,provider)} target="_blank" rel="noreferrer"><Search size={16}/>웹검색 열기<ExternalLink size={13}/></a><p className="text-xs text-gray-500">새 탭 검색 · 회사 내부정보는 검색어에서 제외</p><div className="border-t pt-3 space-y-2"><h4 className="text-sm font-semibold">선택한 웹 자료</h4><label className="block text-sm">웹 자료 제목<input className={input} maxLength={300} value={web.title} onChange={e=>setWeb({...web,title:e.target.value})}/></label><label className="block text-sm">출처 URL<input type="url" className={input} value={web.url} onChange={e=>setWeb({...web,url:e.target.value})}/></label><label className="block text-sm">웹 자료 발췌문<textarea className={`${input} h-24`} value={web.quote} onChange={e=>setWeb({...web,quote:e.target.value})}/></label><button className={button} disabled={disabled || !web.title.trim() || !web.url.trim() || !web.quote.trim() || draft.web.length>=30} onClick={addWebQuote}><Plus size={16}/>웹 자료 넣기</button></div></div>}
      </aside>
    </div>
  </section>;
}
