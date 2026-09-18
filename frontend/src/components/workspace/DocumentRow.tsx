import { useState } from "react";
import { Check, Save, X } from "lucide-react";
import { type SourceDocument, type Workspace } from "@/lib/workspace";
import { ExtractionPages, ArchiveMembers } from "./ExtractionDetails";
import { inputClass, buttonClass, type Mutate } from "./ui";

export default function DocumentRow({doc, ws, prefix, busy, note, mutate}: {doc: SourceDocument; ws: Workspace; prefix: string; busy: boolean; note: string; mutate: Mutate}) {
  const [text, setText] = useState(doc.text || "");
  const [item, setItem] = useState(doc.item_id || "");
  const [attachmentIndex, setAttachmentIndex] = useState(String(doc.attachment_index ?? ""));
  const attachments = (ws.source_attachments || []).filter(a => Number.isInteger(a.index) && a.index >= 1 && a.index <= 10);
  const validAttachment = attachments.some(a => a.index === Number(attachmentIndex));
  return <div className="border-b py-3 space-y-2 min-w-0"><div className="flex flex-wrap justify-between text-sm gap-2"><a className="underline break-all" href={`/api/v2${prefix}/documents/${doc.id}/download`}>{doc.name}</a><span>{{notice_source: "공고 원문", company_evidence: "회사 증빙", product_evidence: "제품 근거", company_reference: "기존 작성자료 · 참고용"}[doc.role]} · {doc.confirmed ? "확인됨" : "미확인"}</span></div>
    {doc.company_asset && <p className="text-sm text-gray-600">중앙 자료 v{doc.company_asset.version} · {doc.company_asset.expires_on ? `만료일 ${doc.company_asset.expires_on}` : doc.company_asset.no_expiry ? "만료 없음 · 담당자 지정" : "기간 미확인"}</p>}
    {doc.asset_issue && <p role="status" className="text-sm text-amber-800">{doc.asset_issue}</p>}
    {doc.role === "notice_source" && attachments.length > 0 && <form className="flex flex-wrap items-end gap-2 min-w-0" onSubmit={e => {
      e.preventDefault();
      if (busy || !validAttachment || !note.trim()) return;
      void mutate(`${prefix}/documents/${encodeURIComponent(doc.id)}/source-link`, {version: ws.version, attachment_index: Number(attachmentIndex), note}, "나라장터 첨부 연결 저장");
    }}>
      <label className="flex-1 min-w-0 text-sm">나라장터 첨부 연결<select required aria-label={`${doc.name} 나라장터 첨부 연결`} className={inputClass} value={attachmentIndex} disabled={busy} onChange={e => setAttachmentIndex(e.target.value)}><option value="">선택</option>{attachments.map(a => <option key={a.index} value={a.index}>{a.index}. {a.name}</option>)}</select></label>
      <button disabled={busy || !validAttachment || !note.trim()} className={buttonClass} aria-label={`${doc.name} 첨부 연결 저장`}><Save size={16}/>연결 저장</button>
    </form>}
    {doc.extraction && <details className="text-sm"><summary>추출 내역 · {doc.extraction.complete ? "본문 확보" : "일부 미확인"}</summary>
      <p role="status">{doc.extraction.complete ? "본문 추출 완료 · 내용 승인은 별도입니다." : "읽지 못한 내용 또는 수식이 있습니다. 원본·변환본을 대조하세요."}</p>
      {doc.extraction.cells && <p>읽은 셀 {doc.extraction.cells.length}개 · 품목 후보 {doc.extraction.items?.length || 0}개</p>}
      {doc.extraction.pages && <ExtractionPages pages={doc.extraction.pages}/>}
      {doc.extraction.issues?.map((issue,i)=><p key={i}>{issue.sheet}!{issue.cell} · {issue.code === "formula_review" ? "수식 값 검토 필요" : "셀 오류 확인 필요"}</p>)}
      {doc.extraction.members && <ArchiveMembers members={doc.extraction.members}/>}
    </details>}
    <details><summary className="text-sm">본문 · {!doc.text ? "분석 불가" : doc.extraction?.complete === false && doc.text_origin !== "manual_confirmed" ? "일부 확인 가능" : "확인 가능"}</summary><textarea aria-label={`${doc.name} 본문`} className={`${inputClass} h-40 mt-2`} value={text} onChange={e => setText(e.target.value)}/>
      <button disabled={busy || !note.trim()} className={buttonClass} onClick={() => void mutate(`${prefix}/documents/${doc.id}/text`, {version: ws.version, text, note})}><Save size={16}/>확인된 본문 저장</button></details>
    {["company_evidence", "product_evidence"].includes(doc.role) && <div className="flex flex-wrap gap-2"><select aria-label={`${doc.name} 연결 서류`} className="border p-2 text-sm" value={item} onChange={e => setItem(e.target.value)}><option value="">필수 서류 연결 없음</option>{ws.inputs.checklist.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      {[true,false].map(confirmed => <button key={String(confirmed)} disabled={busy || !note.trim()} className={buttonClass} onClick={() => void mutate(`${prefix}/documents/${doc.id}/review`, {version: ws.version, role: doc.role, confirmed, checklist_id: item || null, note})}>{confirmed ? <Check size={16}/> : <X size={16}/>} {confirmed ? "증빙 확인" : "증빙 반려"}</button>)}</div>}
  </div>;
}
