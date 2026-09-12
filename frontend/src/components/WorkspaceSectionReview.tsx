"use client";

import { useRef, useState } from "react";
import { Check, Pencil, Save, X } from "lucide-react";
import { Workspace } from "@/lib/workspace";

type Section = NonNullable<Workspace["inputs"]["proposal_sections"]>[number];
const input = "w-full min-w-0 rounded border border-gray-300 bg-white p-2 text-sm";
const button = "inline-flex items-center justify-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-40";

export default function WorkspaceSectionReview({section, ws, prefix, busy, note, mutate}: {
  section: Section; ws: Workspace; prefix: string; busy: boolean; note: string;
  mutate: (path: string, body: unknown, message?: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(section.review_status !== "approved");
  const [localNote, setLocalNote] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const effectiveNote = localNote ?? note;
  const titles = section.title ? [section.title] : ws.inputs.requirements.filter(r => section.requirement_ids?.includes(r.id)).map(r => r.text);
  function submit(approved: boolean | null) {
    if (!formRef.current || !effectiveNote.trim() || busy) return;
    const data = new FormData(formRef.current);
    void mutate(`${prefix}/sections/${section.id}/review`, {
      version: ws.version, text: data.get("text"), note: effectiveNote, approved,
      requirement_ids: data.getAll("requirement_ids"), evidence_ids: data.getAll("evidence_ids"),
    }, approved === null ? "초안 저장 완료 · 검토 대기" : "검토 기록 저장");
  }
  return <form ref={formRef} id={`section-${section.id}`} className="border-t py-4 space-y-3 min-w-0 scroll-mt-6" onSubmit={e => {e.preventDefault(); submit(null);}}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="font-semibold text-base break-words">{titles.join(" · ") || "미연결 초안"}</h3><p className={`text-sm ${section.review_status === "approved" ? "text-green-800" : "text-amber-800"}`}>제안서 섹션 · {section.review_status === "approved" ? "승인" : section.review_status === "rejected" ? "반려" : "검토 대기"} · 근거 {section.evidence_ids.length}개</p></div>
      {!editing && <button ref={editRef} type="button" className={button} onClick={() => {setEditing(true); requestAnimationFrame(() => textRef.current?.focus());}}><Pencil size={16}/>수정</button>}
      {editing && section.review_status === "approved" && <button type="button" className={button} onClick={() => {formRef.current?.reset(); setEditing(false); requestAnimationFrame(() => editRef.current?.focus());}}><X size={16}/>수정 취소</button>}
    </div>
    {section.reference && <details className="text-sm"><summary>기존 작성자료 · {section.reference.name}</summary><blockquote className="border-l-2 pl-3 whitespace-pre-wrap mt-2">{section.reference.quote}</blockquote></details>}
    {section.references?.map((r,i)=><details key={i} className="text-sm"><summary>회사 참고자료 · {r.name}</summary><blockquote className="border-l-2 pl-3 whitespace-pre-wrap mt-2">{r.quote}</blockquote></details>)}
    {section.web_references?.map((r,i)=><details key={i} className="text-sm text-amber-800"><summary>웹 참고자료 · {r.title} · 검증필요</summary><a href={r.url} target="_blank" rel="noreferrer" className="underline break-all">{r.url}</a><blockquote className="whitespace-pre-wrap">{r.quote}</blockquote></details>)}
    <textarea ref={textRef} name="text" aria-label="제안서 섹션 본문" readOnly={!editing} defaultValue={section.text} className={`${input} min-h-32 ${!editing ? "border-transparent bg-gray-50" : ""}`}/>
    <details open={editing && !section.evidence_ids.length} className="text-sm"><summary>{editing ? "연결 수정" : "연결된 요구사항·근거"}</summary>
      <div className="grid sm:grid-cols-2 gap-3 py-3">
        <fieldset className="space-y-1"><legend className="font-medium">대응 요구사항</legend>{ws.inputs.requirements.map(r => <label key={r.id} className={`flex gap-2 ${!editing && !section.requirement_ids?.includes(r.id) ? "hidden" : ""}`}><input type="checkbox" name="requirement_ids" value={r.id} defaultChecked={section.requirement_ids?.includes(r.id)} onClick={e => {if (!editing) e.preventDefault();}} aria-readonly={!editing}/><span className="break-words min-w-0">{r.text}</span></label>)}</fieldset>
        <fieldset className="space-y-1"><legend className="font-medium">확인된 근거 자료</legend>{ws.inputs.documents.filter(d => d.confirmed && ["company_evidence", "product_evidence"].includes(d.role)).map(d => <label key={d.id} className={`flex gap-2 ${!editing && !section.evidence_ids.includes(d.id) ? "hidden" : ""}`}><input type="checkbox" name="evidence_ids" value={d.id} defaultChecked={section.evidence_ids.includes(d.id)} onClick={e => {if (!editing) e.preventDefault();}} aria-readonly={!editing}/><span className="min-w-0 break-words">{d.name}</span></label>)}</fieldset>
      </div>
    </details>
    <label className="block text-sm">섹션 검토 의견<input aria-label="섹션 검토 의견" className={input} value={effectiveNote} onChange={e => setLocalNote(e.target.value)}/></label>
    <div className="flex flex-wrap gap-2">
      {editing && <button disabled={busy || !effectiveNote.trim() || ws.source_changed} className={button}><Save size={16}/>초안 저장</button>}
      {section.review_status !== "approved" || editing ? <button type="button" disabled={busy || !effectiveNote.trim() || ws.source_changed} className={`${button} border-green-700 text-green-800`} onClick={() => submit(true)}><Check size={16}/>내용 승인</button> : null}
      <button type="button" disabled={busy || !effectiveNote.trim() || ws.source_changed} className={button} onClick={() => submit(false)}><X size={16}/>수정 요청</button>
    </div>
  </form>;
}
