"use client";
import {useState} from "react";
import {Check, Plus} from "lucide-react";
import {Workspace, WritingPlanItem, workspaceApi} from "@/lib/workspace";
import {suggestWritingTargets} from "@/lib/writingPlan";

const input="w-full min-w-0 rounded border p-2 text-sm bg-white";
export default function WritingPlanReview({ws,prefix,onSaved,onWriting}:{ws:Workspace;prefix:string;onSaved:(ws:Workspace)=>void;onWriting:()=>void}){
  const [items,setItems]=useState(()=>ws.inputs.writing_plan?.items || suggestWritingTargets(ws.inputs.documents));
  const [excluded,setExcluded]=useState<string[]>([]);
  const [confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [editing,setEditing]=useState(!ws.writing_plan_current);
  const sources=ws.inputs.documents.filter(d=>d.role==="notice_source" && d.text);
  const [manual,setManual]=useState({title:"",document_id:sources[0]?.id || "",quote:""});
  function update(id:string,patch:Partial<WritingPlanItem>){setItems(all=>all.map(i=>i.id===id?{...i,...patch}:i));setConfirmed(false);}
  async function save(){
    setBusy(true);setMessage("저장 중");
    try{
      const result=await workspaceApi<Workspace>(`${prefix}/writing-plan`,{version:ws.version,items:items.filter(i=>!excluded.includes(i.id)),note:"공고 서류 검토 후 작성·첨부 대상 확인"},"PUT");
      onSaved(result);onWriting();
    }catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
  }
  return <section id="writing-plan-review" aria-label="작성 대상 검토" className="border-y py-4 space-y-3">
    <div className="flex flex-wrap justify-between gap-2"><h2 className="text-lg font-semibold">작성·첨부 대상 확인</h2>{ws.writing_plan_current && !editing && <button className="text-sm underline" onClick={()=>setEditing(true)}>대상 수정</button>}</div>
    {ws.writing_plan_current && !editing ? <><p className="text-sm">작성 {items.filter(i=>i.action==="write").length}개 · 원본 첨부 {items.filter(i=>i.action==="attach").length}개 · 전자 제출 {items.filter(i=>i.action==="electronic").length}개</p><button className="border rounded px-3 py-2 text-sm" onClick={onWriting}>확인한 항목 작성하기</button></> : <>
      <p className="text-sm text-gray-600">원문에서 찾은 검토 후보 · 누락·조건 확인 필요</p>
      {ws.inputs.writing_plan && !ws.writing_plan_current && <p role="status" className="text-sm text-amber-800">원문이 변경됐습니다. 작성 대상을 다시 확인하세요. 기존 초안은 보존됩니다.</p>}
      <div className="divide-y">{items.map(item=><div key={item.id} className="py-3 grid sm:grid-cols-[minmax(0,1fr)_140px_150px] gap-2 items-start">
        <div className="min-w-0"><label className="flex gap-2 items-center text-sm"><input type="checkbox" aria-label={`${item.title} 포함`} checked={!excluded.includes(item.id)} onChange={e=>{setExcluded(e.target.checked?excluded.filter(id=>id!==item.id):[...excluded,item.id]);setConfirmed(false);}}/>{item.title}</label><details className="mt-2 text-xs text-gray-600"><summary>공고 근거 확인</summary><blockquote className="whitespace-pre-wrap break-words py-2">{item.quote}</blockquote><a className="underline" href={`/api/v2${prefix}/documents/${item.document_id}/download`}>근거 원문 다운로드</a></details></div>
        <select aria-label={`${item.title} 처리`} className={input} value={item.action} onChange={e=>update(item.id,{action:e.target.value as WritingPlanItem["action"]})}><option value="write">직접 작성</option><option value="attach">발급·원본 첨부</option><option value="electronic">전자 제출</option></select>
        <select aria-label={`${item.title} 구분`} className={input} value={item.document_kind} onChange={e=>update(item.id,{document_kind:e.target.value as WritingPlanItem["document_kind"]})}><option value="qualitative_proposal">정성제안서</option><option value="bid_document">입찰서</option><option value="other_document">기타서류</option></select>
      </div>)}</div>
      <details><summary className="text-sm cursor-pointer">누락된 서류·세부 작성 항목 추가</summary><div className="grid sm:grid-cols-2 gap-2 py-3"><label className="text-sm">원문의 항목명<input className={input} value={manual.title} onChange={e=>setManual({...manual,title:e.target.value})}/></label><label className="text-sm">근거 파일<select className={input} value={manual.document_id} onChange={e=>setManual({...manual,document_id:e.target.value})}>{sources.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label><label className="text-sm sm:col-span-2">항목명이 포함된 원문 인용<textarea className={input} value={manual.quote} onChange={e=>setManual({...manual,quote:e.target.value})}/></label><button className="border rounded px-3 py-2 text-sm inline-flex items-center gap-2" disabled={!manual.title.trim() || !manual.quote.trim() || !manual.document_id} onClick={()=>{setItems([...items,{...manual,id:crypto.randomUUID(),action:"write",document_kind:"other_document"}]);setManual({...manual,title:"",quote:""});setConfirmed(false);}}><Plus size={16}/>항목 추가</button></div></details>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>공고 서류를 검토하고 작성·첨부 대상을 확인했습니다.</label>
      <button disabled={busy || ws.source_changed || !confirmed || !items.some(i=>!excluded.includes(i.id))} className="inline-flex items-center gap-2 bg-red-700 text-white rounded px-3 py-2 text-sm disabled:opacity-40" onClick={()=>void save()}><Check size={16}/>확인 완료 · 비교·작성으로 이동</button>
      {message && <p role="status" className="text-sm">{message}</p>}
    </>}
  </section>;
}
