"use client";

import {FormEvent, useCallback, useEffect, useRef, useState} from "react";
import {ChevronLeft, ChevronRight, Download, FolderOpen, Link2, Pencil, RefreshCw, Save, Search, Upload} from "lucide-react";
import {Modal} from "./Modal";
import {workspaceApi} from "@/lib/workspace";
import {categoryOptions, type AssetCategory, type AssetCategoryCatalog} from "@/lib/companyAssets";

export interface AssetDetails {title:string; category:AssetCategory; subject_business_number:string; issued_on:string|null; expires_on:string|null; no_expiry:boolean; active:boolean}
export interface CompanyAsset {id:string; version:number; details:AssetDetails; validity:string; role:string; file:{name:string; size:number; sha256:string}}
interface AssetList {items:CompanyAsset[]; page:number; has_more:boolean; alerts:Record<string,number>; category_catalog?:AssetCategoryCatalog}
const validityLabels:Record<string,string>={valid:"유효기간 확인", expiring:"30일 내 만료", expired:"만료", unknown:"기간 미확인", disabled:"비활성", not_yet_valid:"발급일 미도래"};
const field="block w-full min-w-0 rounded border border-gray-300 bg-white p-2 text-sm";
const button="inline-flex items-center justify-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-40";

export default function CompanyAssets({noticeNo, version, onLinked}: {noticeNo?:string; version?:number; onLinked?:()=>Promise<unknown>}) {
  const [open,setOpen]=useState(false);
  const [query,setQuery]=useState("");
  const [filter,setFilter]=useState("");
  const [page,setPage]=useState(1);
  const [disabled,setDisabled]=useState(false);
  const [data,setData]=useState<AssetList|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [editor,setEditor]=useState<CompanyAsset|"new"|null>(null);
  const [history,setHistory]=useState<{title:string; items:{version:number; note:string; created_at:string}[]}|null>(null);
  const seq=useRef(0);
  const categories=categoryOptions(data?.category_catalog);
  const refresh=useCallback(async()=>{
    const current=++seq.current;
    try {
      const result=await workspaceApi<AssetList>(`/company-assets?q=${encodeURIComponent(filter)}&page=${page}&include_disabled=${disabled}`);
      if (!Array.isArray(result.items)) throw new Error("중앙 자료 응답을 확인할 수 없습니다.");
      if(current===seq.current)setData(result);
    } catch {if(current===seq.current){setData(null);setMessage("중앙 자료를 불러오지 못했습니다. API 연결과 저장소 마이그레이션 적용을 확인하세요.");}}
  },[filter,page,disabled]);
  useEffect(()=>{if(open)void refresh();return()=>{seq.current++;};},[open,refresh]);
  async function link(asset:CompanyAsset) {
    setBusy(true);setMessage("자료 연결 중");
    try {
      await workspaceApi(`/notices/${encodeURIComponent(noticeNo!)}/company-assets/${asset.id}`,{version,asset_version:asset.version});
      const refreshed=await onLinked?.();setMessage(refreshed===false ? "자료는 연결됐지만 최신 공고 조회에 실패했습니다. 공고를 새로고침하세요." : `${asset.details.title} 연결 완료 · 회사·기간·본문 확인 전 미승인`);
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();const form=new FormData(event.currentTarget);
    const category=categories.find(item=>item.code===form.get("category"));
    if(!category){setMessage("자료 분류를 확인한 뒤 다시 저장하세요.");return;}
    const details:AssetDetails={title:String(form.get("title")),category:category.code,subject_business_number:String(form.get("subject")),issued_on:String(form.get("issued"))||null,expires_on:String(form.get("expires"))||null,no_expiry:form.has("no_expiry"),active:editor==="new"||form.has("active")};
    setBusy(true);setMessage("자료 저장 중");
    try {
      if(editor==="new") {
        const body=new FormData();body.set("metadata",JSON.stringify(details));body.set("file",form.get("file")!);
        await workspaceApi("/company-assets",body);
      }else if(editor){await workspaceApi(`/company-assets/${editor.id}`,{version:editor.version,details,note:String(form.get("note"))},"PUT");}
      setEditor(null);await refresh();setMessage("중앙 자료 저장 완료 · 연결된 공고의 변경 자료는 재검토가 필요합니다.");
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  const item=editor && editor!=="new" ? editor : null;
  return <section aria-label="회사 자료 보관소" className="min-w-0 border-y py-3 space-y-3">
    <button type="button" className={button} aria-expanded={open} onClick={()=>setOpen(!open)}><FolderOpen size={16}/>{noticeNo ? "중앙 회사자료 연결" : "회사 자료 보관소"}</button>
    {open && <>
      <div role="status" aria-label="중앙 자료 결과" className="text-sm break-words">{message}</div>
      {data && <p className="text-sm text-amber-800">만료 {data.alerts.expired||0}개 · 30일 내 만료 {data.alerts.expiring||0}개 · 기간 미확인 {data.alerts.unknown||0}개</p>}
      {data && !categories.length && <p role="status" className="text-sm text-amber-800">자료 분류를 불러오지 못했습니다. 새로고침 후 등록·수정하세요. 원본 조회와 다운로드는 가능합니다.</p>}
      <form className="flex flex-wrap items-end gap-2" onSubmit={e=>{e.preventDefault();setPage(1);setFilter(query);}}>
        <label className="text-sm flex-1 min-w-0">자료 검색<input className={field} value={query} onChange={e=>setQuery(e.target.value)}/></label>
        <button className={button} aria-label="중앙 자료 검색" title="검색"><Search size={16}/></button>
        <button className={button} type="button" onClick={()=>void refresh()} aria-label="중앙 자료 새로고침" title="새로고침"><RefreshCw size={16}/></button>
        {!noticeNo && <button className={button} type="button" disabled={!categories.length} onClick={()=>setEditor("new")}><Upload size={16}/>자료 등록</button>}
        <label className="text-sm"><input type="checkbox" checked={disabled} onChange={e=>{setDisabled(e.target.checked);setPage(1);}}/> 비활성 포함</label>
      </form>
      <div className="overflow-x-auto"><table className="w-full text-sm" aria-label="중앙 회사자료"><thead><tr className="border-b text-left"><th className="p-2">자료</th><th className="p-2">회사·유효기간</th><th className="p-2">상태</th><th className="p-2">작업</th></tr></thead><tbody>{data?.items.map(asset=><tr key={asset.id} className="border-b align-top">
        <td className="p-2 min-w-36"><strong className="break-words">{asset.details.title}</strong><p>{categories.find(item=>item.code===asset.details.category)?.label || "분류 확인 필요"} · v{asset.version}</p></td>
        <td className="p-2 min-w-36">{asset.details.subject_business_number || "회사 주체 미등록"}<p>{asset.details.expires_on || (asset.details.no_expiry ? "만료 없음 · 담당자 지정" : "유효기간 미확인")}</p></td>
        <td className={`p-2 min-w-28 ${asset.validity==="valid" ? "text-green-800" : "text-amber-800"}`}>{validityLabels[asset.validity]||"미확인"}</td>
        <td className="p-2"><div className="flex flex-wrap gap-2 min-w-28"><a className={button} title="원본 다운로드" aria-label={`${asset.details.title} 원본 다운로드`} href={`/api/v2/company-assets/${asset.id}/download`}><Download size={16}/></a>
        {noticeNo ? <button className={button} disabled={busy||!asset.details.active} onClick={()=>void link(asset)} aria-label={`${asset.details.title} 연결`}><Link2 size={16}/>연결</button> : <>
          <button className={button} disabled={busy||!categories.some(item=>item.code===asset.details.category)} title="자료 정보 수정" aria-label={`${asset.details.title} 수정`} onClick={()=>setEditor(asset)}><Pencil size={16}/></button>
          <button className={button} onClick={async()=>{try{const result=await workspaceApi<{items:{version:number;note:string;created_at:string}[]}>(`/company-assets/${asset.id}/history`);setHistory({title:asset.details.title,items:result.items});}catch(error){setMessage((error as Error).message);}}}>이력</button>
        </>}</div></td>
      </tr>)}</tbody></table></div>
      {data?.items.length===0 && <p className="text-sm">등록된 자료가 없습니다.</p>}
      <div className="flex items-center gap-3"><button className={button} disabled={page===1} onClick={()=>setPage(page-1)} aria-label="자료 이전 페이지" title="이전 페이지"><ChevronLeft size={16}/></button><span className="text-sm">{page} 페이지</span><button className={button} disabled={!data?.has_more} onClick={()=>setPage(page+1)} aria-label="자료 다음 페이지" title="다음 페이지"><ChevronRight size={16}/></button></div>
      {noticeNo && <a className="text-sm underline" href="/admin#assets">중앙 자료 등록·유효기간 관리</a>}
    </>}
    <Modal open={editor!==null} onClose={()=>{if(!busy)setEditor(null);}} title={item ? "중앙 자료 수정" : "중앙 자료 등록"}>
      <form key={item?.id||"new"} onSubmit={save} className="space-y-3">
        <label className="block text-sm">자료명<input name="title" required maxLength={200} defaultValue={item?.details.title} className={field}/></label>
        <label className="block text-sm">자료 분류<select name="category" defaultValue={item?.details.category||categories[0]?.code} className={field}>{categories.map(option=><option key={option.code} value={option.code}>{option.label}</option>)}</select></label>
        <label className="block text-sm">문서 주체 사업자번호<input name="subject" defaultValue={item?.details.subject_business_number} className={field}/></label>
        <div className="grid sm:grid-cols-2 gap-3"><label className="text-sm">발급일<input name="issued" type="date" defaultValue={item?.details.issued_on||""} className={field}/></label><label className="text-sm">만료일<input name="expires" type="date" defaultValue={item?.details.expires_on||""} className={field}/></label></div>
        <label className="block text-sm"><input type="checkbox" name="no_expiry" defaultChecked={item?.details.no_expiry}/> 원문에서 유효기간 제한 없음을 확인함</label>
        {item ? <><label className="block text-sm"><input name="active" type="checkbox" defaultChecked={item.details.active}/> 활성 자료</label><label className="block text-sm">변경 사유<textarea required name="note" className={field}/></label></> : <label className="block text-sm">원본 파일<input required name="file" type="file" accept=".pdf,.hwp,.hwpx,.xlsx" className="block w-full text-sm"/></label>}
        <p role="status" className="text-sm text-amber-800 break-words">{message}</p><button className={button} disabled={busy||!categories.length}><Save size={16}/>저장</button>
      </form>
    </Modal>
    <Modal open={!!history} onClose={()=>setHistory(null)} title="중앙 자료 변경 이력"><h3>{history?.title}</h3><ul className="divide-y">{history?.items.map(event=><li key={event.version} className="py-2 text-sm">v{event.version} · {new Date(event.created_at).toLocaleString("ko-KR")}<p className="break-words">{event.note}</p></li>)}</ul></Modal>
  </section>;
}
