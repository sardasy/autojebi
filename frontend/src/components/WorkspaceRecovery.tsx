"use client";

import { useMemo, useState } from "react";
import { Check, Save } from "lucide-react";
import { QuoteDiagnostic, SourceNeed, Workspace, WorkspaceJob, workspaceApi } from "@/lib/workspace";
import { isDuplicateRequirement } from "@/lib/requirementDuplicates";

const input = "block w-full min-w-0 border rounded p-2 text-sm bg-white";
const button = "inline-flex items-center gap-2 border rounded px-3 py-2 text-sm disabled:opacity-40";
const states = {exact: "원문 일치", whitespace: "공백 차이", ambiguous: "위치 중복", mismatch: "불일치", invalid_structure: "응답 형식 오류"};

function exactLocations(text: string, quote: string) {
  const locations: {start: number; line: number; context: string}[] = [];
  if (!quote.trim()) return locations;
  let previousIndex = 0;
  let start = 0;
  let line = 1;
  for (let index = text.indexOf(quote); index !== -1; index = text.indexOf(quote, index + 1)) {
    const between = text.slice(previousIndex, index);
    // The API uses Python character offsets, which count supplementary Unicode characters once.
    start += Array.from(between).length;
    line += between.split("\n").length - 1;
    const from = Math.max(0, index - 35);
    const to = Math.min(text.length, index + quote.length + 35);
    locations.push({start, line, context: `${from ? "…" : ""}${text.slice(from, to).replace(/\s+/g, " ")}${to < text.length ? "…" : ""}`});
    previousIndex = index;
  }
  return locations;
}

export function QuoteRecovery({job, ws, prefix, reload}: {job: WorkspaceJob; ws: Workspace; prefix: string; reload: () => Promise<unknown>}) {
  return <section aria-label="AI 인용 복구" className="space-y-3 border-t pt-3">
    <h3 className="font-semibold text-sm">원문 대조·후보 채택</h3>
    {job.result?.quote_diagnostics?.map(candidate => <Candidate key={`${candidate.candidate_id}-${ws.version}`} candidate={candidate} job={job} ws={ws} prefix={prefix} reload={reload}/>) }
  </section>;
}

function Candidate({candidate, job, ws, prefix, reload}: {candidate: QuoteDiagnostic; job: WorkspaceJob; ws: Workspace; prefix: string; reload: () => Promise<unknown>}) {
  const req = candidate.requirement;
  const [quote, setQuote] = useState(candidate.matches[0]?.quote || req?.quote || "");
  const [selectedStart, setSelectedStart] = useState(-1);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState("");
  const [requestKey] = useState(() => crypto.randomUUID());
  const doc = ws.inputs.documents.find(d => d.id === req?.document_id && d.role === "notice_source");
  const locations = useMemo(() => exactLocations(doc?.text || "", quote), [doc?.text, quote]);
  const suggestions = [...new Set(candidate.matches.map(match => match.quote))];
  const start = locations.length === 1 ? locations[0].start : selectedStart;
  const duplicate = isDuplicateRequirement(ws.inputs.requirements, {document_id: req?.document_id, quote, text: req?.text});
  const valid = locations.some(location => location.start === start);
  const canAdopt = valid && !!note.trim() && !duplicate && !ws.source_changed && !pending;
  const changeQuote = (value: string) => {setQuote(value); setSelectedStart(-1); setStatus("");};
  const locationStatus = !doc?.text ? "원문이 없어 인용을 확인할 수 없습니다." : !quote.trim()
    ? "원문에서 인용할 문장을 입력하세요." : locations.length === 0
      ? "교정 인용과 정확히 일치하는 원문이 없습니다. 숫자·단위·부정 표현과 공백을 확인하세요."
      : locations.length === 1 ? "원문에서 정확히 일치하는 위치 1곳을 찾았습니다."
        : valid ? "선택한 위치가 원문과 정확히 일치합니다." : `원문에서 ${locations.length}곳이 일치합니다. 앞뒤 문맥을 보고 위치를 선택하세요.`;
  if (!req) return <p className="text-sm text-red-700">후보 {candidate.candidate_id}: 응답 형식 오류</p>;
  return <details className="border-b py-2"><summary className="cursor-pointer text-sm">{states[candidate.status]} · {req.text}{duplicate ? " · 기존 항목과 중복" : ""}</summary>
    <form className="space-y-3 pt-3" onSubmit={async e => {
      e.preventDefault(); if (!canAdopt) return; setPending(true); setStatus("채택 중");
      try {await workspaceApi(`${prefix}/jobs/${job.id}/adopt-requirements`, {version: ws.version, idempotency_key: requestKey, note,
        items: [{candidate_id: candidate.candidate_id, quote, start, locator: req.locator}]}); setStatus("검토 대기·미판정으로 저장했습니다."); await reload();}
      catch(error) {setStatus((error as Error).message);} finally {setPending(false);}
    }}>
      <div className="grid md:grid-cols-2 gap-3"><div><p className="text-sm font-medium">AI 인용</p><p className="whitespace-pre-wrap text-sm break-words">{req.quote}</p></div>
        <div><p className="text-sm font-medium">원문 · {doc?.name || "문서 없음"}</p><pre className="text-sm whitespace-pre-wrap break-words max-h-64 overflow-auto">{doc?.text || "원문 없음"}</pre></div></div>
      {suggestions.length > 1 && <label className="block text-sm">원문 인용 후보<select className={input} value={suggestions.includes(quote) ? quote : ""} onChange={e => changeQuote(e.target.value)}><option value="">직접 교정</option>{suggestions.map((suggestion, index) => <option key={suggestion} value={suggestion}>{index + 1}. {suggestion}</option>)}</select></label>}
      <label className="block text-sm">교정 인용<textarea className={input} value={quote} onChange={e => changeQuote(e.target.value)}/></label>
      <p className="text-xs text-gray-600">숫자·단위·부정 표현을 포함해 원문 그대로 인용하세요. 일치하는 위치를 자동으로 찾습니다.</p>
      {locations.length > 1 && <label className="block text-sm">원문 위치 선택<select className={input} value={start} onChange={e => {setSelectedStart(Number(e.target.value)); setStatus("");}}><option value={-1}>앞뒤 문맥을 보고 위치를 선택하세요</option>{locations.map((location, index) => <option key={location.start} value={location.start}>{index + 1}번째 · {location.line}행: {location.context}</option>)}</select></label>}
      <label className="block text-sm">채택 의견<input className={input} required value={note} onChange={e => setNote(e.target.value)}/></label>
      <button className={button} disabled={!canAdopt}><Check size={16}/>이 후보 채택</button>
      <p role="status" className="text-sm">{status || locationStatus}</p>
    </form>
  </details>;
}

export function SourceNeeds({ws, prefix, reload}: {ws: Workspace; prefix: string; reload: () => Promise<unknown>}) {
  if (!ws.source_needs?.length) return null;
  return <section aria-label="별도 참조 문서" className="border-y py-3 space-y-2"><h2 className="font-semibold">본문에서 참조하는 문서</h2>
    {ws.source_needs.map(need => <Need key={`${need.id}-${ws.version}`} need={need} ws={ws} prefix={prefix} reload={reload}/>)}
  </section>;
}

function Need({need, ws, prefix, reload}: {need: SourceNeed; ws: Workspace; prefix: string; reload: () => Promise<unknown>}) {
  const [state, setState] = useState(need.state);
  const [documentId, setDocumentId] = useState(need.linked_document_id || "");
  const [quote, setQuote] = useState(need.resolution_quote || "");
  const [locator, setLocator] = useState("");
  const [note, setNote] = useState(need.note || "");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  return <details className="border-b py-2"><summary className="text-sm cursor-pointer">{need.name} · {{missing: "확보·해당 여부 확인 필요", linked: "원문 연결 확인", not_applicable: "해당 없음 확인"}[need.state]}</summary>
    <form className="space-y-2 pt-3" onSubmit={async e => {e.preventDefault(); setBusy(true); try {
      await workspaceApi(`${prefix}/source-needs`, {version: ws.version, items: [{id: need.id, state, document_id: documentId, resolution_quote: quote, note, locator}]}, "PUT");
      setStatus("확인 기록 저장 완료"); await reload();
    } catch(error) {setStatus((error as Error).message);} finally {setBusy(false);}}}>
      {need.mentions.map(m => <blockquote key={m.document_id} className="border-l-2 pl-3 whitespace-pre-wrap text-sm">{m.quote}</blockquote>)}
      {!!need.candidates?.length && <label className="block text-sm">내부 파일·원문 연결 후보<select className={input} defaultValue="" onChange={e => {const candidate = need.candidates?.[Number(e.target.value)]; if (candidate && e.target.value !== "") {setDocumentId(candidate.document_id); setQuote(candidate.quote); setLocator(candidate.locator);}}}><option value="">후보 선택 · 확보 상태는 직접 확인하세요</option>{need.candidates.map((c, i) => <option key={`${c.document_id}-${i}`} value={i}>{c.member_path.join(" / ") || c.locator} · {c.quote.slice(0, 100)}</option>)}</select>{locator && <p className="break-all">위치: {locator}</p>}</label>}
      <label className="block text-sm">확보 상태<select className={input} value={state} onChange={e => setState(e.target.value as SourceNeed["state"])}><option value="missing">미확보·확인 필요</option><option value="linked">파일 연결 확인</option><option value="not_applicable">해당 없음 확인</option></select></label>
      <label className="block text-sm">확인 원문<select className={input} value={documentId} onChange={e => {setDocumentId(e.target.value); setLocator("");}}><option value="">선택</option>{ws.inputs.documents.filter(d => d.role === "notice_source").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <label className="block text-sm">확인 근거 인용<textarea className={input} value={quote} onChange={e => {setQuote(e.target.value); setLocator("");}}/></label>
      <label className="block text-sm">확인 의견<input className={input} required value={note} onChange={e => setNote(e.target.value)}/></label>
      <button className={button} disabled={busy || ws.source_changed || !note.trim()}><Save size={16}/>문서 확인 저장</button><p role="status" className="text-sm">{status}</p>
    </form>
  </details>;
}
