"use client";

import {useState} from "react";
import {Workspace, workspaceApi} from "@/lib/workspace";

interface Candidate {
  id: string; document_id: string; document_name: string; document_sha256: string | null;
  source_text_sha256: string; text: string; quote: string; start: number; end: number; locator: string;
  category: "technical" | "qualification" | "document" | "schedule"; signals: string[];
}
interface Candidates {
  version: number; items: Candidate[]; scanned_characters: number; source_document_count: number;
  limited: boolean; warnings: string[];
}

const field = "block w-full min-w-0 border rounded p-2 text-sm bg-white";
const button = "border rounded px-3 py-2 text-sm disabled:opacity-40";

export default function WorkspaceRequirementCandidates({ws, prefix, reload}: {
  ws: Workspace; prefix: string; reload: () => Promise<unknown>;
}) {
  const [result, setResult] = useState<Candidates | null>(null);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState("");
  const [savedQuotes, setSavedQuotes] = useState<string[]>([]);
  const stale = !!result && result.version !== ws.version;
  return <section aria-label="원문 요구사항 후보" className="border rounded p-3 space-y-3">
    <h3 className="font-semibold">원문에서 요구사항 복구</h3>
    <p className="text-sm">의무·수량·기한·제출 표현이 있는 원문 행을 검토 후보로 찾습니다. 완전한 요구사항 추출이나 충족 판정이 아니며, 앞뒤 문맥과 나머지 원문을 직접 확인해야 합니다.</p>
    <button type="button" className={button} disabled={pending || ws.source_changed} onClick={async () => {
      setPending(true); setStatus(""); setResult(null);
      try {
        const value = await workspaceApi<Candidates>(`${prefix}/requirement-candidates?version=${ws.version}`);
        setResult(value);
        setStatus(value.items.length ? `${value.items.length}개 검토 후보를 찾았습니다.` : "명시 표현을 가진 후보를 찾지 못했습니다. 원문을 직접 검토하고 요구사항을 등록하세요.");
      } catch (error) {setStatus((error as Error).message);} finally {setPending(false);}
    }}>{pending ? "원문 확인 중" : "원문에서 요구사항 후보 찾기"}</button>
    <p role="status" className="text-sm">{stale ? "입력이 변경되었습니다. 현재 원문에서 후보를 다시 찾으세요." : status}</p>
    {result?.warnings.map(warning => <p key={warning} className="text-sm text-amber-800">{warning}</p>)}
    {result?.items.map(candidate => <CandidateCard key={`${result.version}-${candidate.id}`} candidate={candidate} ws={ws} prefix={prefix} reload={reload} stale={stale}
      locallySaved={savedQuotes.includes(JSON.stringify([ws.version, candidate.document_id, candidate.quote]))}
      onSaved={() => setSavedQuotes(previous => [...previous, JSON.stringify([ws.version, candidate.document_id, candidate.quote])])}/>)}
  </section>;
}

function CandidateCard({candidate, ws, prefix, reload, stale, locallySaved, onSaved}: {
  candidate: Candidate; ws: Workspace; prefix: string; reload: () => Promise<unknown>; stale: boolean;
  locallySaved: boolean; onSaved: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [checked, setChecked] = useState(false);
  const [category, setCategory] = useState(candidate.category);
  const [mandatory, setMandatory] = useState(true);
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [status, setStatus] = useState("");
  const doc = ws.inputs.documents.find(document => document.id === candidate.document_id && document.role === "notice_source");
  const exact = !!doc?.text && Array.from(doc.text).slice(candidate.start, candidate.end).join("") === candidate.quote && candidate.text === candidate.quote;
  const duplicate = locallySaved || ws.inputs.requirements.some(requirement => requirement.document_id === candidate.document_id && (requirement.quote === candidate.quote || requirement.text === candidate.text));
  const valid = checked && exact && !duplicate && !stale && !ws.source_changed && !pending && !saved;
  return <details className="border-t pt-2" onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary className="cursor-pointer text-sm">{candidate.text.slice(0, 90)}{candidate.text.length > 90 ? "…" : ""}{duplicate ? " · 이미 등록됨" : ""}</summary>
    {expanded && <form className="space-y-3 pt-3" onSubmit={async event => {
      event.preventDefault(); if (!valid) return;
      setPending(true); setStatus("검토 대기로 저장 중");
      try {
        await workspaceApi(`${prefix}/requirements`, {version: ws.version, document_id: candidate.document_id,
          text: candidate.text, quote: candidate.quote, locator: candidate.locator, category, mandatory,
          review_status: "pending", compliance: "unassessed"});
        setSaved(true); onSaved(); setStatus("검토 대기·미판정으로 저장했습니다."); await reload();
      } catch (error) {setStatus((error as Error).message);} finally {setPending(false);}
    }}>
      <p className="text-sm">{candidate.document_name} · {candidate.locator} · {candidate.signals.join(" / ")}</p>
      <blockquote className="whitespace-pre-wrap break-words border-l-2 pl-3 text-sm">{candidate.quote}</blockquote>
      <div><p className="font-medium text-sm">대조할 현재 원문</p><pre className="whitespace-pre-wrap break-words max-h-64 overflow-auto text-sm">{doc?.text || "원문 없음"}</pre></div>
      <label className="block text-sm">요구사항 종류<select className={field} value={category} onChange={event => setCategory(event.target.value as Candidate["category"])}><option value="technical">기술·규격</option><option value="qualification">참가 자격</option><option value="document">제출 서류</option><option value="schedule">기한·일정</option></select></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={mandatory} onChange={event => setMandatory(event.target.checked)}/>필수 요구사항으로 검토</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)}/>앞뒤 문맥과 숫자·단위·부정 표현을 확인했습니다</label>
      <button type="submit" className={button} disabled={!valid}>검토 대기 요구사항으로 저장</button>
      <p role="status" className="text-sm">{status || (!exact ? "현재 원문과 후보가 일치하지 않습니다. 다시 찾으세요." : duplicate ? "이미 등록된 요구사항입니다." : "")}</p>
    </form>}
  </details>;
}
