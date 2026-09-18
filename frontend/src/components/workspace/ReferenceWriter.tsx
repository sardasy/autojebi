import { useState } from "react";
import { Save } from "lucide-react";
import { type Workspace } from "@/lib/workspace";
import { inputClass, buttonClass, type Mutate } from "./ui";

export default function ReferenceWriter({ws, prefix, busy, note, mutate}: {ws: Workspace; prefix: string; busy: boolean; note: string; mutate: Mutate}) {
  const references = ws.inputs.documents.filter(d => d.role === "company_reference");
  const [requirementId, setRequirementId] = useState(ws.inputs.requirements[0]?.id || "");
  const [referenceId, setReferenceId] = useState(references[0]?.id || "");
  const [quote, setQuote] = useState("");
  const [text, setText] = useState("");
  const requirement = ws.inputs.requirements.find(r => r.id === requirementId);
  const reference = references.find(d => d.id === referenceId);
  const values = (value: string) => [...value.matchAll(/\d+(?:[.,]\d+)?\s*(?:개월|대|일|년|시간|개|%)/g)].map(match => match[0]).join(" · ") || "수치 미확인";
  return <form className="space-y-4" onSubmit={e => {
    e.preventDefault();
    void mutate(`${prefix}/reference-drafts`, {version: ws.version, requirement_id: requirementId, document_id: referenceId, quote, text, note}, "비교 작성 초안 저장 완료 · 사실 확인 대기");
  }}>
    <h2 className="font-semibold">공고와 기존 작성자료 비교</h2>
    <div className="overflow-x-auto"><table aria-label="요구사항 비교표" className="w-full min-w-[620px] text-sm text-left"><thead className="bg-gray-100"><tr>{["항목", "이전 작성자료", "이번 공고 요구", "작성 상태"].map(label => <th key={label} className="p-3">{label}</th>)}</tr></thead><tbody>{ws.inputs.requirements.map(r => {
      const section = ws.inputs.proposal_sections?.find(s => s.requirement_ids?.includes(r.id));
      return <tr key={r.id} className={`border-b ${r.id === requirementId ? "bg-red-50" : ""}`}><th className="p-3 font-medium">{r.text}</th><td className="p-3">{values((r.id === requirementId && quote) || section?.reference?.quote || "")}</td><td className="p-3">{values(r.quote)}</td><td className="p-3">{section?.review_status === "approved" ? "내용 승인" : section ? "검토 필요" : "미작성"}</td></tr>;
    })}</tbody></table></div>
    {!ws.inputs.requirements.length && <p role="status" className="text-sm text-amber-800">등록된 요구사항이 없습니다. 공고 서류 검토에서 원문 요구사항을 등록하세요.</p>}
    {!references.length && <p role="status" className="text-sm text-amber-800">회사 기존 작성자료가 없습니다. 이전 제안서나 작성 문서를 등록하세요.</p>}
    <div className="grid md:grid-cols-2 gap-4">
      <div className="min-w-0 space-y-2"><label className="text-sm">이번 공고 요구사항<select required className={inputClass} value={requirementId} onChange={e => setRequirementId(e.target.value)}><option value="">선택</option>{ws.inputs.requirements.map(r => <option key={r.id} value={r.id}>{r.text}</option>)}</select></label>
        <blockquote className="whitespace-pre-wrap break-words border-l-2 pl-3 text-sm">{requirement?.quote || "원문 미선택"}</blockquote><p className="text-xs text-gray-500">{requirement?.locator}</p>
      </div>
      <div className="min-w-0 space-y-2"><label className="text-sm">기존 작성자료<select required className={inputClass} value={referenceId} onChange={e => {setReferenceId(e.target.value); setQuote("");}}><option value="">선택</option>{references.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        <div className="max-h-60 overflow-y-auto whitespace-pre-wrap break-words text-sm border-l-2 pl-3">{reference?.text || "본문 미확인 · 본문 추출 또는 확인된 본문 등록 필요"}</div>
      </div>
    </div>
    <label className="block text-sm">참고할 원문 인용<textarea required className={`${inputClass} h-24`} value={quote} onChange={e => setQuote(e.target.value)}/></label>
    {!!quote && !reference?.text.includes(quote) && <p role="status" className="text-sm text-amber-800">인용문이 기존 작성자료와 일치하지 않습니다.</p>}
    {!!quote && requirement && <p className="border-l-4 border-amber-500 pl-3 text-sm">수치 대조 · 이전 {values(quote)} → 요구 {values(requirement.quote)} · 담당자 확인 필요</p>}
    <label className="block text-sm">이번 공고에 맞춘 작성 내용<textarea required className={`${inputClass} h-48`} value={text} onChange={e => setText(e.target.value)}/></label>
    <p className="text-sm text-amber-800">기존 작성자료는 참고용입니다. 이번 공고의 사실·수치·증빙은 별도 확인이 필요합니다.</p>
    <button disabled={busy || ws.source_changed || !note.trim() || !requirement || !text.trim() || !quote.trim() || !reference?.text.includes(quote)} className={buttonClass}><Save size={16}/>비교 작성 초안 저장</button>
  </form>;
}
