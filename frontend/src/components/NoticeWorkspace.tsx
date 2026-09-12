"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ArrowLeft, ExternalLink } from "lucide-react";
import type { NoticeRecord, ProposalCoverageResponse } from "@/lib/api";
import { nextNoticeAction, nextNoticeTab, documentSummaryText, readDocumentAutomation } from "@/lib/documentAutomation";
import { NoticeActionsBar } from "./NoticeActionsBar";
import { DocumentPreparationPanel, HwpJobs } from "./DocumentPreparationPanel";
import { SpecItemsPanel } from "./SpecItemsPanel";
import { ExportButtonGroup } from "./ExportButtonGroup";
import { StatusBadge } from "./StatusBadge";
import { ProposalCoveragePanel } from "./ProposalCoveragePanel";
import { ProposalActions } from "./ProposalActions";

const tabs = [
  ["review", "공고 검토"], ["documents", "서류 준비"], ["spec", "규격 대응"],
  ["proposal", "제안서"], ["exports", "생성/검토"],
] as const;
type Tab = typeof tabs[number][0];
const anchors: Record<string, Tab> = { "work-actions": "review", grading: "review", documents: "documents", "spec-items": "spec", "proposal-readiness": "proposal", exports: "exports" };

export function NoticeWorkspace({ notice, coverage, coverageError }: { notice: NoticeRecord; coverage: ProposalCoverageResponse | null; coverageError: string | null }) {
  const [tab, setTab] = useState<Tab>("review");
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const docs = readDocumentAutomation(notice);
  useEffect(() => {
    const sync = () => {
      const query = new URLSearchParams(location.search).get("tab");
      const anchor = anchors[location.hash.slice(1)];
      setTab(anchor || (tabs.some(([key]) => key === query) ? query as Tab : "review"));
    };
    sync(); window.addEventListener("popstate", sync); window.addEventListener("hashchange", sync);
    return () => { window.removeEventListener("popstate", sync); window.removeEventListener("hashchange", sync); };
  }, []);
  const select = (value: Tab) => {
    setTab(value); const url = new URL(location.href); url.searchParams.set("tab", value); url.hash = "";
    history.pushState(null, "", url);
  };
  const next = nextNoticeAction(notice);
  const nextTab = nextNoticeTab(notice);
  const raw = notice.raw || {};
  const grade = (notice.analysis?.grade || {}) as Record<string, unknown>;
  const qualNotes = Array.isArray(grade.qual_notes) ? grade.qual_notes : [];
  const originalUrl = String(raw.bidNtceDtlUrl || raw.bidNtceUrl || "");
  const safeUrl = /^https?:\/\//.test(originalUrl) ? originalUrl : null;
  return <div className="min-w-0">
    <Link href="/notices" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-600"><ArrowLeft size={16}/>공고 작업대</Link>
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 basis-full sm:basis-0"><div className="mb-2 flex flex-wrap gap-2 text-xs text-slate-500"><StatusBadge value={notice.status}/><span>{notice.notice_no}</span></div>
          <h1 className="text-xl font-semibold">{notice.title || notice.notice_no}</h1>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600"><span>{notice.org_name || "기관 미확인"}</span><span>마감 {notice.close_date ? new Date(notice.close_date).toLocaleString("ko-KR") : "미확인"}</span><span>담당 {notice.assignee || "미배정"}</span></div>
        </div>
        <button className="work-button work-primary shrink-0" onClick={() => select(nextTab)}>{next}<ArrowRight size={16}/></button>
      </div>
    </header>
    <div className="flex flex-wrap gap-x-4 gap-y-1 border-b border-slate-200 py-2 text-xs text-slate-600"><span>{docs ? documentSummaryText(docs) : "서류 분석 전"}</span><span>규격 후보 {notice.spec_item_count || 0}개 · 요구값 확인 {notice.spec_value_count || 0}개</span></div>
    <div role="tablist" aria-label="공고 업무" className="mt-3 flex max-w-full overflow-x-auto border-b border-slate-200">
      {tabs.map(([key, label], index) => <button key={key} ref={el => { refs.current[index] = el; }} id={`tab-${key}`} role="tab" aria-selected={tab === key} aria-controls={`panel-${key}`} tabIndex={tab === key ? 0 : -1}
        onClick={() => select(key)} onKeyDown={e => {
          const target = e.key === "ArrowRight" ? (index + 1) % tabs.length : e.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : -1;
          if (target >= 0) { e.preventDefault(); select(tabs[target][0]); refs.current[target]?.focus(); }
        }} className={`shrink-0 border-b-2 px-4 py-3 text-sm ${tab === key ? "border-red-700 font-semibold text-red-700" : "border-transparent text-slate-600"}`}>{label}</button>)}
    </div>
    <section id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="min-w-0 py-5">
      {tab === "review" && <>
        <NoticeActionsBar notice={notice}/>
        {qualNotes.length > 0 && <div className="work-band"><h2 className="font-semibold">자격 평가 메모</h2><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{qualNotes.map((note, index) => <li key={index}>{String(note)}</li>)}</ul></div>}
        <details className="work-band text-sm"><summary>공고 상세정보</summary><dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">{[["수요기관", raw.dminsttNm], ["입찰방식", raw.bidMethdNm], ["계약방법", raw.cntrctCnclsMthdNm], ["공고일", notice.open_date], ["개찰일", raw.opengDt], ["제품 유사도", notice.sku_match_score]].map(([label, value]) => <div key={String(label)}><dt className="text-xs text-slate-500">{String(label)}</dt><dd className="break-words">{String(value ?? "미확인")}</dd></div>)}</dl></details>
        <div className="work-band grid grid-cols-2 gap-4 md:grid-cols-4">{[["사양", notice.score_spec], ["자격", notice.score_qual], ["가격", notice.score_price], ["종합", notice.score_total]].map(([label,value]) => <div key={String(label)}><p className="text-sm text-slate-500">{label}</p><p className="mt-1 text-xl font-semibold">{typeof value === "number" ? `${Math.round(value*100)}점` : "미평가"}</p></div>)}</div>
        <div className="work-band grid gap-5 md:grid-cols-2"><div><h2 className="font-semibold">추천 제품</h2><p className="mt-2">{notice.top_sku_name || "추천 제품 없음"}</p><p className="text-xs text-slate-500">{notice.top_sku}</p></div><div><h2 className="font-semibold">검토 의견</h2><p className="mt-2 text-sm">{notice.grade_reason || "분석 결과 없음"}</p><p className="mt-2 text-sm text-amber-800">{notice.risk_note}</p></div></div>
        <div className="work-band"><h2 className="font-semibold">공고 원문</h2><p className="my-2 text-sm">예가 {notice.base_price == null ? "미확인" : `${Number(notice.base_price).toLocaleString("ko-KR")}원`}</p>{safeUrl && <a href={safeUrl} target="_blank" rel="noreferrer" className="work-button">원문 열기<ExternalLink size={16}/></a>}<details className="mt-4 text-sm"><summary>기술 상세</summary><pre className="mt-2 max-h-64 overflow-auto text-xs">{JSON.stringify(notice.analysis?.elec_spec || {}, null, 2)}</pre></details></div>
      </>}
      {tab === "documents" && <DocumentPreparationPanel notice={notice} view="documents"/>}
      {tab === "spec" && <SpecItemsPanel notice={notice} enabled={Boolean(docs)}/>}
      {tab === "proposal" && <div className="space-y-6"><ProposalActions noticeNo={notice.notice_no}/><ProposalCoveragePanel coverage={coverage} error={coverageError}/><SpecItemsPanel notice={notice} enabled={Boolean(docs)} mode="proposal"/></div>}
      {tab === "exports" && <div className="space-y-6"><ExportButtonGroup noticeNo={notice.notice_no} exports={docs?.exports || []}/><HwpJobs noticeNo={notice.notice_no} jobs={docs?.hwp_jobs || []} exports={docs?.exports || []}/>{!docs?.hwp_jobs?.length && <p className="text-sm text-slate-600">생성된 HWP 작업이 없습니다.</p>}</div>}
    </section>
  </div>;
}
