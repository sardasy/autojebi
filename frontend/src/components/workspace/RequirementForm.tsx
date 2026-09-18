import { useState } from "react";
import { Save } from "lucide-react";
import { type Requirement, type Workspace } from "@/lib/workspace";
import { inputClass, buttonClass, type Mutate } from "./ui";

export default function RequirementForm({req, ws, prefix, busy, mutate}: {req?: Requirement; ws: Workspace; prefix: string; busy: boolean; mutate: Mutate}) {
  const [open, setOpen] = useState(!req);
  return <details id={req ? `requirement-${req.id}` : undefined} open={open} onToggle={e => setOpen(e.currentTarget.open)} className="border-b py-2"><summary className="text-sm">{req ? `${req.text} · ${{pending: "검토 필요", accepted: "확인", rejected: "반려"}[req.review_status]}` : "원문 요구사항"}</summary>
    <form className="grid sm:grid-cols-2 gap-3 pt-3" onSubmit={e => {
      e.preventDefault(); const data = new FormData(e.currentTarget);
      void mutate(`${prefix}/requirements`, {version: ws.version, id: req?.id || null, text: data.get("text"), document_id: data.get("document_id"), quote: data.get("quote"), locator: data.get("locator"), category: data.get("category"), mandatory: data.get("mandatory") === "on", proposed_value: data.get("proposed_value"), evidence_id: data.get("evidence_id") || null, evidence_quote: data.get("evidence_quote"), evidence_locator: data.get("evidence_locator"), review_status: data.get("review_status"), compliance: data.get("compliance"), proposal_disposition: data.get("proposal_disposition"), proposal_note: data.get("proposal_note")});
    }}>
      <label className="text-sm">요구사항<input required className={inputClass} name="text" defaultValue={req?.text}/></label>
      <label className="text-sm">공고 원문<select required name="document_id" className={inputClass} defaultValue={req?.document_id || ""}><option value="">선택</option>{ws.inputs.documents.filter(d => d.role === "notice_source").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <label className="text-sm">원문 인용<textarea required className={inputClass} name="quote" defaultValue={req?.quote}/></label><label className="text-sm">원문 페이지·문단<input required className={inputClass} name="locator" defaultValue={req?.locator}/></label>
      <label className="text-sm">유형<select className={inputClass} name="category" defaultValue={req?.category || "technical"}><option value="technical">기술 규격</option><option value="qualification">자격</option><option value="document">서류</option><option value="schedule">일정</option></select></label>
      <label className="text-sm flex items-center gap-2"><input type="checkbox" name="mandatory" defaultChecked={req?.mandatory ?? true}/>필수</label>
      <label className="text-sm">제안값<textarea className={inputClass} name="proposed_value" defaultValue={req?.proposed_value}/></label>
      <label className="text-sm">확인된 근거<select className={inputClass} name="evidence_id" defaultValue={req?.evidence_id || ""}><option value="">없음</option>{ws.inputs.documents.filter(d => ["company_evidence", "product_evidence"].includes(d.role) && d.confirmed).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <label className="text-sm">근거 인용<textarea className={inputClass} name="evidence_quote" defaultValue={req?.evidence_quote}/></label><label className="text-sm">근거 페이지·문단<input className={inputClass} name="evidence_locator" defaultValue={req?.evidence_locator}/></label>
      <label className="text-sm">제안서 반영<select name="proposal_disposition" className={inputClass} defaultValue={req?.proposal_disposition || "include"}><option value="include">본문 대응 필수</option><option value="evidence_only">별도 증빙으로 충족</option></select></label>
      <label className="text-sm">별도 증빙 충족 사유<input name="proposal_note" className={inputClass} defaultValue={req?.proposal_note || ""}/></label>
      <label className="text-sm">담당자 충족 판정<select className={inputClass} name="compliance" defaultValue={req?.compliance || "unassessed"}><option value="unassessed">미판정</option><option value="meets">충족</option><option value="does_not_meet">미충족</option></select></label>
      <label className="text-sm">검토 상태<select className={inputClass} name="review_status" defaultValue={req?.review_status || "pending"}><option value="pending">검토 필요</option><option value="accepted">확인</option><option value="rejected">반려</option></select></label><button disabled={busy} className={buttonClass}><Save size={16}/>저장</button>
    </form>
  </details>;
}
