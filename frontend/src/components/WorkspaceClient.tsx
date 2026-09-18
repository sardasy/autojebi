"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Play, RefreshCw } from "lucide-react";
import { workspaceApi } from "@/lib/workspace";
import { Prerequisites } from "./WorkspacePrerequisites";
import { SelectedWritingEvidence } from "./DocumentWritingWorkspace";
import WorkspaceIdentity from "./WorkspaceIdentity";
import { actorLabel, buttonClass, date, inputClass, stepIds, Tab, tabs } from "./workspace/ui";
import { deriveWorkspace, NextAction, nextStep as selectNextStep } from "./workspace/derive";
import { useWorkspace } from "./workspace/useWorkspace";
import SourceReviewTab from "./workspace/SourceReviewTab";
import WritingTab from "./workspace/WritingTab";
import ReviewTab, { HwpPreview } from "./workspace/ReviewTab";
import JobHistory from "./workspace/JobHistory";

/** v2 workspace shell: header, next action, tab navigation. Data lives in useWorkspace; tabs render the steps. */
export default function WorkspaceClient({noticeNo}: {noticeNo: string}) {
  const prefix = `/notices/${encodeURIComponent(noticeNo)}`;
  const [picked, setPicked] = useState<(SelectedWritingEvidence & {noticeNo: string}) | null>(null);
  const [tab, setTab] = useState<Tab>(tabs[0]);
  const [note, setNote] = useState("");
  const [template, setTemplate] = useState("bid_form");
  const [hwpVisible, setHwpVisible] = useState(false);
  const [scrollTarget, setScrollTarget] = useState<string | null>(null);
  const [templates, setTemplates] = useState<{template_key: string; name: string}[]>([]);
  const [templateError, setTemplateError] = useState("");
  useEffect(() => {
    let stopped = false;
    workspaceApi<{items: {template_key: string; name: string}[]}>("/hwp-templates")
      .then(result => {if (!Array.isArray(result.items)) throw new Error("invalid templates"); if (!stopped) {setTemplates(result.items); setTemplate(current => result.items.some(t => t.template_key === current) ? current : result.items[0]?.template_key || "");}})
      .catch(() => {if (!stopped) setTemplateError("HWP 템플릿을 불러오지 못했습니다. 연결 확인 후 새로고침하세요.");});
    return () => {stopped = true;};
  }, []);
  const [prerequisites, setPrerequisites] = useState<Prerequisites | null>(null);
  const [focusRequirement, setFocusRequirement] = useState<string | null>(null);
  const [recoveryConfirmed, setRecoveryConfirmed] = useState<Record<string, boolean>>({});
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<HwpPreview | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  function activateTab(name: Tab) {
    setTab(name);
    window.history.replaceState(null, "", `#${stepIds[tabs.indexOf(name)]}`);
  }
  function goTo(name: Tab, target = "workspace-panel") {
    activateTab(name); setScrollTarget(target);
  }
  useEffect(() => {
    if (!scrollTarget) return;
    const element = document.getElementById(scrollTarget);
    let parent: HTMLElement | null = element;
    while (parent) {if (parent instanceof HTMLDetailsElement) parent.open = true; parent = parent.parentElement;}
    element?.scrollIntoView?.({block: "start", behavior: "smooth"});
    element?.focus({preventScroll: true});
    setScrollTarget(null);
  }, [scrollTarget, tab]);
  useEffect(() => {
    if (!focusRequirement || tab !== tabs[0]) return;
    const element = document.getElementById(`requirement-${focusRequirement}`) as HTMLDetailsElement | null;
    if (element) {element.open = true; element.scrollIntoView?.({block: "center"}); element.querySelector("summary")?.focus();}
    setFocusRequirement(null);
  }, [focusRequirement, tab]);
  useEffect(() => {
    const sync = () => {
      const hash = window.location.hash.slice(1);
      const index = stepIds.indexOf(hash);
      if (index >= 0) setTab(tabs[index]);
      else if (hash.startsWith("section-") || hash === "generated-files") setTab(tabs[2]);
    };
    sync(); window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const {ws, setWs, loading, status, setStatus, feedback, busy, trackedJob, reload, mutate, run: runJob} = useWorkspace(prefix, {
    onMutated: () => {setPreview(null); setRecoveryConfirmed({});},
  });
  const run = (kind: string) => runJob(kind, {template_key: template, visible: hwpVisible});
  const plannedTemplateKeys = ws?.inputs.output_plan?.template_keys.join("\0");
  useEffect(() => {
    const planned = plannedTemplateKeys?.split("\0");
    if (planned?.length) setTemplate(current => planned.includes(current) ? current : planned[0]);
  }, [plannedTemplateKeys]);
  const derived = deriveWorkspace(ws);
  const nextStep = selectNextStep(ws, prefix, derived);
  const perform = (action: NextAction) => {
    if (action.type === "mutate") void mutate(action.path, action.body, action.message);
    else if (action.type === "run") void run(action.kind);
    else goTo(action.tab, action.target);
  };
  return <div className="min-w-0 space-y-4">
    <WorkspaceIdentity/>
    <Link href="/workspace" className="text-sm underline">1. 공고 찾기</Link>
    {!ws ? <><p role="status">{loading ? "서류 불러오는 중" : status}</p>{!loading && <button disabled={busy} className={buttonClass} onClick={() => void mutate(`${prefix}/initialize`, {}, "서류 검토 시작")}><Play size={16}/>검토 시작</button>}</> : <>
      <header className="border-b pb-4 flex flex-wrap justify-between gap-3">
        <div className="min-w-0"><p className="text-xs text-gray-500">{noticeNo} · 입력 버전 {ws.version}</p><h1 className="text-xl font-semibold break-keep [overflow-wrap:anywhere]">{ws.inputs.notice.title || noticeNo}</h1>
          <p className="text-sm text-gray-600 mt-2">{ws.inputs.notice.org_name || "기관 미확인"} · {ws.inputs.notice.close_date ? date(ws.inputs.notice.close_date) : "마감 미확인"}</p></div>
        <div className="text-sm"><strong>{ws.ready ? "서류 확인 완료" : "서류 확인 필요"}</strong><p>요구사항 {ws.inputs.requirements.length}개 · 초안 {ws.inputs.proposal_sections?.length || 0}개</p></div>
      </header>
      {ws.inputs.legacy_warning && <p className="border-l-4 border-amber-500 pl-3 text-sm">과거 분석 오류·보류 이력이 있습니다. 기존 점수와 승인은 새 판단으로 승계하지 않았습니다.</p>}
      {nextStep && <section aria-label="지금 할 작업" className="border-l-4 border-red-700 bg-gray-50 px-4 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0 flex-1 basis-60"><p className="text-xs text-gray-500 mb-1">지금 할 작업</p><h2 className="text-base font-semibold break-words">{nextStep.title}</h2></div>
        {nextStep.href ? <Link href={nextStep.href} className={`${buttonClass} bg-red-700 text-white border-red-700`}>{nextStep.label}<ArrowRight size={16}/></Link> : <button disabled={busy || nextStep.disabled} onClick={() => {if (nextStep.action) perform(nextStep.action);}} className={`${buttonClass} bg-red-700 text-white border-red-700`}>{nextStep.label}{nextStep.disabled ? <RefreshCw size={16} className="animate-spin"/> : <ArrowRight size={16}/>}</button>}
      </section>}
      <details className="text-sm"><summary className="cursor-pointer text-gray-600">검토 의견·상태 관리</summary><div className="flex flex-wrap items-end gap-2 pt-3">
        <label className="flex-1 min-w-40 text-sm">검토 의견<input className={inputClass} value={note} onChange={e => setNote(e.target.value)} aria-label="검토 의견"/></label>
        <button disabled={busy} className={buttonClass} title="최신 상태" aria-label="최신 상태" onClick={() => void reload()}><RefreshCw size={18}/></button>
        {ws.source_changed && <button disabled={busy} className={buttonClass} onClick={() => void mutate(`${prefix}/sync`, {version: ws.version}, "원문 동기화 완료")}>원문 동기화</button>}
      </div></details>
      <p role="status" aria-label="실행 결과" aria-live="polite" className={`text-sm break-words ${feedback === "error" ? "text-red-700" : feedback === "success" ? "text-green-800" : "text-gray-600"}`}>{ws.jobs.find(j => j.id === trackedJob)?.error?.code === "unverified_quote" ? "" : status}</p>
      <div role="tablist" aria-label="검토 단계" className="flex border-b overflow-x-auto">{tabs.map((name, index) => <button key={name} id={`tab-${index}`} ref={el => {tabRefs.current[index] = el;}} role="tab" aria-selected={tab === name} aria-controls="workspace-panel" tabIndex={tab === name ? 0 : -1} className={`px-4 py-3 text-sm whitespace-nowrap ${tab === name ? "border-b-2 border-red-700 font-semibold" : "text-gray-500"}`} onClick={() => activateTab(name)} onKeyDown={e => {
        const next = e.key === "ArrowRight" ? (index+1)%tabs.length : e.key === "ArrowLeft" ? (index+tabs.length-1)%tabs.length : e.key === "Home" ? 0 : e.key === "End" ? tabs.length-1 : -1;
        if(next >= 0) {e.preventDefault(); activateTab(tabs[next]); tabRefs.current[next]?.focus();}
      }}>{name}</button>)}</div>
      <section role="tabpanel" id="workspace-panel" tabIndex={-1} aria-labelledby={`tab-${tabs.indexOf(tab)}`} className="space-y-4 min-w-0 scroll-mt-4">
      {tab === tabs[0] && <SourceReviewTab ws={ws} prefix={prefix} noticeNo={noticeNo} busy={busy} note={note} derived={derived}
        mutate={mutate} run={run} reload={reload} setWs={setWs} goTo={goTo} activateTab={activateTab}/>}
      <WritingTab ws={ws} tab={tab} prefix={prefix} noticeNo={noticeNo} busy={busy} note={note} picked={picked} setPicked={setPicked}
        setWs={setWs} setPreview={setPreview} mutate={mutate} run={run} reload={reload} goTo={goTo} activateTab={activateTab}/>
      <ReviewTab ws={ws} tab={tab} prefix={prefix} busy={busy} note={note} mutate={mutate} run={run} goTo={goTo}
        setWs={setWs} setStatus={setStatus} setFocusRequirement={setFocusRequirement}
        template={template} setTemplate={setTemplate} templates={templates} templateError={templateError}
        hwpVisible={hwpVisible} setHwpVisible={setHwpVisible} preview={preview} setPreview={setPreview}
        prerequisites={prerequisites} setPrerequisites={setPrerequisites}/>
      <JobHistory ws={ws} tab={tab} prefix={prefix} busy={busy} note={note} mutate={mutate} reload={reload} hwpVisible={hwpVisible}
        reviewNotes={reviewNotes} setReviewNotes={setReviewNotes} recoveryConfirmed={recoveryConfirmed} setRecoveryConfirmed={setRecoveryConfirmed}/>
      <details><summary className="text-sm">변경·검토 이력</summary>{ws.reviews.map(r => <div className="border-t pt-2 text-sm" key={r.id}><strong>버전 {r.input_version}</strong> · {date(r.created_at)}<p>{r.note}</p><p className="text-xs text-gray-500">{actorLabel(r.actor)}</p></div>)}</details>
      </section>
    </>}
  </div>;
}
