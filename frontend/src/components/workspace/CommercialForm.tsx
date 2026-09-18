import { Save } from "lucide-react";
import { type Workspace } from "@/lib/workspace";
import { inputClass, buttonClass, type Mutate } from "./ui";

export default function CommercialForm({ws, prefix, busy, mutate}: {ws: Workspace; prefix: string; busy: boolean; mutate: Mutate}) {
  const price = ws.inputs.commercial;
  return <details className="border-y py-3"><summary>제안 총액·견적 근거</summary><form className="grid sm:grid-cols-2 gap-3 pt-3" onSubmit={e => {
    e.preventDefault(); const form = new FormData(e.currentTarget);
    void mutate(`${prefix}/commercial`, {version: ws.version, offer_price: Number(form.get("offer_price")), quantity: Number(form.get("quantity")), document_id: form.get("document_id"), quote: form.get("quote"), locator: form.get("locator"), note: form.get("note")});
  }}>
    <label className="text-sm">제안 총액 (원)<input className={inputClass} name="offer_price" type="number" min="0.01" step="0.01" required defaultValue={price?.offer_price}/></label>
    <label className="text-sm">수량<input className={inputClass} name="quantity" type="number" min="1" step="1" required defaultValue={price?.quantity || 1}/></label>
    <label className="text-sm">확인된 견적 자료<select className={inputClass} name="document_id" required defaultValue={price?.document_id || ""}><option value="">선택</option>{ws.inputs.documents.filter(d => d.confirmed && ["company_evidence", "product_evidence"].includes(d.role)).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
    <label className="text-sm">견적 페이지·문단<input className={inputClass} name="locator" required defaultValue={price?.locator}/></label>
    <label className="text-sm">원화 총액 원문 인용<textarea className={inputClass} name="quote" required defaultValue={price?.quote}/></label>
    <label className="text-sm">담당자 확인 의견<textarea className={inputClass} name="note" required defaultValue={price?.note}/></label>
    <button disabled={busy || ws.source_changed} className={buttonClass}><Save size={16}/>견적 근거 저장</button>
  </form></details>;
}
