"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Download, FileText, Play, RefreshCw, Save, Upload, X } from "lucide-react";
import { ExtractedArchiveMember, ExtractedPage, jobNames, jobStates, Requirement, SourceAttachment, SourceDocument, Workspace, WorkspaceActor, workspaceApi } from "@/lib/workspace";
import WorkspaceWorkerStatus from "./WorkspaceWorkerStatus";
import WorkspaceHwpStatus from "./WorkspaceHwpStatus";
import WorkspaceSectionReview from "./WorkspaceSectionReview";
import WorkspaceDocumentViewer from "./WorkspaceDocumentViewer";
import WorkspacePrerequisites, { Prerequisites } from "./WorkspacePrerequisites";
import { QuoteRecovery, SourceNeeds } from "./WorkspaceRecovery";
import { WorkspaceJob } from "@/lib/workspace";
import NoticeBrief from "./NoticeBrief";
import DocumentWritingWorkspace, {SelectedWritingEvidence} from "./DocumentWritingWorkspace";
import WritingPlanReview from "./WritingPlanReview";
import NoticeFormWorkspace from "./NoticeFormWorkspace";
import CompanyAssets from "./CompanyAssets";
import SpecificationWorkbench from "./SpecificationWorkbench";
import WorkspaceOutputPlan from "./WorkspaceOutputPlan";
import WorkspaceArtifactReview from "./WorkspaceArtifactReview";
import WorkspaceDecision from "./WorkspaceDecision";
import WorkspaceIdentity from "./WorkspaceIdentity";
import WorkspaceRequirementCandidates from "./WorkspaceRequirementCandidates";

const inputClass = "block border border-gray-300 rounded p-2 w-full min-w-0 bg-white text-sm";
const buttonClass = "inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 border rounded px-3 py-2 text-sm disabled:opacity-40";
const tabs = ["2. 공고 서류 검토", "3. 비교·작성", "4. 서류 확인"] as const;
const fieldLabels: Record<string, string> = {business_number: "사업자번호", ceo_name: "대표자명", address: "주소", org_name: "공고 기관", company_name: "회사명"};
const readableError = (message: string) => message.replace(/\b(business_number|ceo_name|address|org_name|company_name)\b/g, key => fieldLabels[key]);
const actorLabel = (actor?: WorkspaceActor | null) => actor ? `${actor.name} · ${{viewer: "조회자", writer: "작성자", reviewer: "검토자", approver: "최종 승인자"}[actor.role]}` : "개인 식별 정보 없음";

export default function WorkspaceClient({noticeNo}: {noticeNo: string}) {
  const prefix = `/notices/${encodeURIComponent(noticeNo)}`;
  const [ws, setWs] = useState<Workspace | null>(null);
  const [picked, setPicked] = useState<(SelectedWritingEvidence & {noticeNo: string}) | null>(null);
  const [tab, setTab] = useState<typeof tabs[number]>(tabs[0]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [feedback, setFeedback] = useState<"loading" | "success" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [template, setTemplate] = useState("bid_form");
  const [hwpVisible, setHwpVisible] = useState(false);
  const [trackedJob, setTrackedJob] = useState<string | null>(null);
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
  const [preview, setPreview] = useState<{input_version: number; values: Record<string, string>; required_missing: string[]} | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const stepIds = ["documents", "writing", "review"];
  function activateTab(name: typeof tabs[number]) {
    setTab(name);
    window.history.replaceState(null, "", `#${stepIds[tabs.indexOf(name)]}`);
  }
  function goTo(name: typeof tabs[number], target = "workspace-panel") {
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
      const index = ["documents", "writing", "review"].indexOf(hash);
      if (index >= 0) setTab(tabs[index]);
      else if (hash.startsWith("section-") || hash === "generated-files") setTab(tabs[2]);
    };
    sync(); window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const reload = useCallback(async () => {
    try {setWs(await workspaceApi<Workspace>(`${prefix}/workspace`)); return true;}
    catch(e) {setStatus((e as Error).message); setFeedback("error"); return false;} finally {setLoading(false);}
  }, [prefix]);
  useEffect(() => {void reload();}, [reload]);
  const plannedTemplateKeys = ws?.inputs.output_plan?.template_keys.join("\0");
  useEffect(() => {
    const planned = plannedTemplateKeys?.split("\0");
    if (planned?.length) setTemplate(current => planned.includes(current) ? current : planned[0]);
  }, [plannedTemplateKeys]);
  useEffect(() => {
    if (!ws?.jobs.some(j => j.status === "running" || j.status === "queued")) return;
    const timer = setInterval(() => void reload(), 2000);
    return () => clearInterval(timer);
  }, [ws, reload]);
  async function mutate(path: string, body: unknown, message = "저장 완료") {
    setTrackedJob(null);
    setBusy(true); setStatus("처리 중"); setFeedback("loading");
    try {
      const result = await workspaceApi<Partial<WorkspaceJob> | null>(path, body);
      const jobId = result?.id && result?.kind && result?.status ? result.id : null;
      const refreshed = await reload();
      setPreview(null); setRecoveryConfirmed({});
      if (refreshed && jobId) setTrackedJob(jobId);
      else if (refreshed) {setStatus(message); setFeedback("success");}
      else {setStatus("요청은 처리됐지만 최신 조회에 실패했습니다. 최신 상태 버튼으로 확인하세요.");}
    }
    catch(e) {setStatus((e as Error).message); setFeedback("error");} finally {setBusy(false);}
  }
  async function run(kind: string) {
    if (!ws) return;
    setBusy(true); setFeedback("loading"); setStatus("작업 접수 중");
    try {
      const job = await workspaceApi<WorkspaceJob>(`${prefix}/jobs`, {kind, input_version: ws.version, idempotency_key: crypto.randomUUID(), template_key: template, visible: hwpVisible});
      setTrackedJob(job.id); await reload();
    } catch(error) {setFeedback("error"); setStatus((error as Error).message);}
    finally {setBusy(false);}
  }
  useEffect(() => {
    const job = ws?.jobs.find(item => item.id === trackedJob);
    if (!job) return;
    const waiting = ["queued", "running"].includes(job.status);
    setFeedback(waiting ? "loading" : job.status === "succeeded" ? "success" : "error");
    setStatus(`${jobNames[job.kind]} · ${jobStates[job.status]}${job.quality === "warning" ? " · 경고·검토 필요" : ""}${job.error ? ` · ${job.error.message} ${job.error.next_action}` : ""}`);
  }, [ws, trackedJob]);
  const date = (value: string) => new Date(value).toLocaleString("ko-KR");
  const layoutReviewed = (job: WorkspaceJob) => {
    const review = ws?.reviews.find(r => r.job_id === job.id);
    return job.kind === "hwp" && job.input_version === ws?.version && review?.action === "approved"
      && review.layout_confirmed && review.output_sha256 === job.result?.sha256;
  };
  const latestHwp = ws?.jobs.find(j => j.kind === "hwp");
  const hwpBlocked = latestHwp?.input_version === ws?.version && ["failed", "blocked"].includes(latestHwp?.status || "");
  const hwpMissing = hwpBlocked && latestHwp?.error?.code === "required_missing";
  const needsSourceReview = !ws?.inputs.source_reviewed || !ws.inputs.requirements.length || ws.source_attachments?.some(a => a.state !== "ready") || ws.source_needs?.some(n => n.state === "missing");
  const sourceDocuments = ws?.inputs.documents.filter(d => d.role === "notice_source") || [];
  const hasSourceText = sourceDocuments.some(d => d.text?.trim());
  const pendingFetch = ws?.jobs.find(j => j.kind === "fetch" && j.status === "succeeded" && j.input_version === ws.version && j.result?.documents?.some(d => d.role === "notice_source" && !ws.inputs.documents.some(existing => existing.id === d.id)));
  const pendingExtract = ws?.jobs.find(j => j.kind === "extract" && j.status === "succeeded" && j.input_version === ws.version && j.result?.documents?.some(d => d.text?.trim() && sourceDocuments.some(source => source.id === d.id && source.text !== d.text)));
  const activeJob = ws?.jobs.find(j => ["queued", "running"].includes(j.status));
  const unreadSource = sourceDocuments.some(d => !d.text?.trim());
  const missingAttachment = ws?.source_attachments?.some(a => a.state === "missing");
  const nextStep = (() => {
    if (!ws) return null;
    if (activeJob) return {title: `${jobNames[activeJob.kind]} · ${jobStates[activeJob.status]}`, label: "처리 중", action: () => {}, disabled: true};
    if (ws.source_changed) return {title: "공고 원문이 변경되었습니다", label: "최신 원문 동기화", action: () => void mutate(`${prefix}/sync`, {version: ws.version}, "원문 동기화 완료")};
    if (pendingFetch) return {title: "첨부 다운로드 완료 · 검토 자료에 반영 대기", label: "다운로드한 첨부 반영", action: () => void mutate(`${prefix}/jobs/${pendingFetch.id}/apply`, {version: ws.version}, "첨부 반영 완료 · 본문 추출이 필요합니다.")};
    if (missingAttachment || !sourceDocuments.length) return {title: "검토할 공고 원문이 필요합니다", label: "누락 첨부 가져오기", action: () => void run("fetch")};
    if (pendingExtract) return {title: "본문 추출 완료 · 분석 입력에 반영 대기", label: "추출한 본문 반영", action: () => void mutate(`${prefix}/jobs/${pendingExtract.id}/apply`, {version: ws.version}, "본문 반영 완료")};
    if (!hasSourceText || unreadSource) return {title: "첨부 파일의 본문을 읽어야 합니다", label: "원문 본문 추출", action: () => void run("extract")};
    if (ws.writing_plan_current) {
      const missing = ws.inputs.writing_plan?.items.filter(item=>item.action==="write" && !ws.inputs.proposal_sections?.some(s=>s.id===item.id && s.text.trim())) || [];
      if(missing.length) return {title: `공고에서 확인한 작성 항목 ${missing.length}개가 남았습니다`,label:"비교·작성",action:()=>goTo(tabs[1])};
    }
    if (!ws.inputs.requirements.length) return {title: "제출서류와 주요 사항을 확인하세요", label: "공고 핵심 확인", action: () => goTo(tabs[0], "notice-brief")};
    if (hwpMissing) return {title: "HWP 필수 입력값 확인이 필요합니다", label: "회사정보 확인", href: "/admin#company"};
    if (hwpBlocked) return {title: "HWP 생성 차단 사유를 확인하세요", label: "생성 결과 확인", action: () => goTo(tabs[2], "generated-files")};
    if (needsSourceReview) return {title: "제출서류와 주요 사항을 확인하세요", label: "공고 핵심 확인", action: () => goTo(tabs[0], "notice-brief")};
    if (!ws.inputs.proposal_sections?.length) return {title: "기존 작성자료와 비교해 초안을 작성하세요", label: "비교·작성", action: () => goTo(tabs[1])};
    if (ws.ready) return {title: "제출 준비 확인 완료", label: "최종 패키지 확인", action: () => goTo(tabs[2], "generated-files")};
    return {title: ws.next_action, label: "서류 확인", action: () => goTo(tabs[2])};
  })();
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
        {nextStep.href ? <Link href={nextStep.href} className={`${buttonClass} bg-red-700 text-white border-red-700`}>{nextStep.label}<ArrowRight size={16}/></Link> : <button disabled={busy || nextStep.disabled} onClick={nextStep.action} className={`${buttonClass} bg-red-700 text-white border-red-700`}>{nextStep.label}{nextStep.disabled ? <RefreshCw size={16} className="animate-spin"/> : <ArrowRight size={16}/>}</button>}
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
      {tab === tabs[0] && <>
        {hasSourceText && <NoticeBrief documents={ws.inputs.documents} prefix={prefix}/>}
        {hasSourceText && <WritingPlanReview key={`plan-${ws.version}`} ws={ws} prefix={prefix} onSaved={setWs} onWriting={()=>goTo(tabs[1])}/>}
        <details id="source-details" className="border-y py-3" open={!hasSourceText}><summary className="text-sm cursor-pointer font-medium">원문·상세 검토</summary><div className="space-y-4 pt-4">
        <details className="border-b pb-3" open={hasSourceText}><summary className="text-sm font-medium cursor-pointer">다른 원문 작업</summary><div className="space-y-3 pt-3">
        <div role="status" aria-label="원문 준비 상태" className="border-l-4 border-amber-500 pl-3 text-sm space-y-2">
          {ws.source_changed ? <p>원문·회사 정보가 변경되었습니다. 원문 동기화가 필요합니다.</p> : pendingFetch ? <><p>내려받은 첨부가 아직 검토 대상에 반영되지 않았습니다.</p><button disabled={busy} className={buttonClass} onClick={() => void mutate(`${prefix}/jobs/${pendingFetch.id}/apply`, {version: ws.version}, "첨부 반영 완료 · 본문 추출이 필요합니다.")}><Check size={16}/>첨부 결과 반영</button></> : pendingExtract ? <><p>추출한 본문이 아직 분석 입력에 반영되지 않았습니다.</p><button disabled={busy} className={buttonClass} onClick={() => void mutate(`${prefix}/jobs/${pendingExtract.id}/apply`, {version: ws.version}, "본문 반영 완료 · 요구사항 분석이 가능합니다.")}><Check size={16}/>본문 결과 반영</button></> : !sourceDocuments.length ? <p>등록된 공고 원문이 없습니다. 첨부 가져오기 또는 공고 원문 등록이 필요합니다.</p> : !hasSourceText ? <p>공고 파일은 등록됐지만 본문이 없습니다. 본문 추출 또는 확인된 본문 등록이 필요합니다.</p> : <p>분석 가능한 공고 본문 {sourceDocuments.filter(d => d.text?.trim()).length}개 · 전체 원문 대조와 요구사항 검토는 별도입니다.</p>}
        </div>
        <div className="flex flex-wrap gap-2"><button disabled={busy || ws.source_changed} className={buttonClass} onClick={() => void run("fetch")}><Download size={16}/>첨부 가져오기</button><button disabled={busy || ws.source_changed || !ws.inputs.documents.length} className={buttonClass} onClick={() => void run("extract")}><FileText size={16}/>본문 추출</button>
          <button disabled={busy || ws.source_attachments?.some(attachment => attachment.state !== "ready")} className={buttonClass} onClick={() => void mutate(`${prefix}/source-review`, {version: ws.version, text: "confirmed", note}, "원문 대조 확인 저장")}><Check size={16}/>원문 전체 대조 확인</button></div>
        <button disabled={busy || ws.source_changed || !hasSourceText} className={buttonClass} onClick={() => void run("analyze")}><Play size={16}/>요구사항 분석</button>
        </div></details>
        {!!ws.source_attachments?.length && <SourceInventory attachments={ws.source_attachments} pendingIndexes={pendingFetch?.result?.documents?.filter(d => d.role === "notice_source").map(d => d.attachment_index).filter((i): i is number => typeof i === "number")}/>}
        <SourceNeeds ws={ws} prefix={prefix} reload={reload}/>
        {(sourceDocuments.length > 0 || ws.inputs.requirements.length > 0) && <div className="grid lg:grid-cols-2 gap-6 items-start"><WorkspaceDocumentViewer documents={ws.inputs.documents.filter(d => d.role === "notice_source")} prefix={prefix}/><div className="min-w-0">
        <h2 className="font-semibold">요구사항 {ws.inputs.requirements.length}개</h2>
        <WorkspaceRequirementCandidates ws={ws} prefix={prefix} reload={reload}/>
        {ws.inputs.requirements.map(req => <RequirementForm key={`${req.id}-${ws.version}`} req={req} ws={ws} busy={busy} prefix={prefix} mutate={mutate}/>)}
        <details id="source-requirement-entry" className="border-y py-3"><summary>요구사항 추가</summary><RequirementForm ws={ws} busy={busy} prefix={prefix} mutate={mutate}/></details>
        </div></div>}
        <details className="border-y py-3"><summary className="text-sm font-medium cursor-pointer">원문·증빙 파일 관리 · {ws.inputs.documents.filter(d => d.role !== "company_reference").length}개</summary>
        <form className="flex flex-wrap gap-2 items-end border-y py-3" onSubmit={e => {e.preventDefault(); const form = new FormData(e.currentTarget); form.set("version", String(ws.version)); void mutate(`${prefix}/documents`, form, "파일 등록 완료");}}>
          <label className="text-sm">문서 구분<select name="role" className={inputClass}><option value="notice_source">공고 원문</option><option value="company_evidence">회사 증빙</option><option value="product_evidence">제품 근거</option></select></label>
          <label className="text-sm min-w-0">파일<input name="file" type="file" required className="block max-w-full"/></label><button disabled={busy} className={buttonClass}><Upload size={16}/>등록</button>
        </form>
        <CompanyAssets noticeNo={noticeNo} version={ws.version} onLinked={reload}/>
        {ws.inputs.documents.filter(doc => doc.role !== "company_reference").map(doc => <DocumentRow key={`${doc.id}-${ws.version}`} doc={doc} ws={ws} prefix={prefix} busy={busy} note={note} mutate={mutate}/>)}
        {!sourceDocuments.length && !ws.inputs.requirements.length && <details id="source-requirement-entry" className="py-3"><summary className="text-sm cursor-pointer">원문 요구사항 수동 등록</summary><RequirementForm ws={ws} busy={busy} prefix={prefix} mutate={mutate}/></details>}
        </details>
        <button className={buttonClass} onClick={() => activateTab(tabs[1])}>비교·작성으로 이동</button>
        </div></details>
      </>}
      <div hidden={tab !== tabs[1]} className="space-y-5">
        <NoticeFormWorkspace ws={ws} prefix={prefix} busy={busy} onSaved={updated => {setWs(updated);setPreview(null);}}/>
        <SpecificationWorkbench noticeNo={noticeNo} version={ws.version} onChanged={async () => {await reload();}} onChooseEvidence={evidence => setPicked({...evidence, key: crypto.randomUUID(), noticeNo})}/>
        <DocumentWritingWorkspace key={noticeNo} ws={ws} prefix={prefix} busy={busy} selectedEvidence={picked?.noticeNo === noticeNo ? picked : null} onSaved={updated => {setWs(updated);setPreview(null);}} onRefresh={reload} onReview={()=>goTo(tabs[0],"writing-plan-review")}/>
        <details id="writing-reference-files" className="border-t pt-3"><summary className="text-sm font-semibold cursor-pointer">회사 참고자료 등록·본문 확인</summary><div className="space-y-3 pt-3">
        <form className="flex flex-wrap gap-3 items-end border-b pb-3" onSubmit={e => {e.preventDefault(); const form = new FormData(e.currentTarget); form.set("version", String(ws.version)); form.set("role", "company_reference"); void mutate(`${prefix}/documents`, form, "기존 작성자료 등록 완료");}}>
          <label className="text-sm min-w-0">회사 기존 작성자료<input name="file" type="file" required className="block max-w-full"/></label><button disabled={busy} className={buttonClass}><Upload size={16}/>작성자료 등록</button>
          <button type="button" disabled={busy} className={buttonClass} onClick={() => void run("extract")}><FileText size={16}/>본문 추출</button>
        </form>
        <CompanyAssets noticeNo={noticeNo} version={ws.version} onLinked={reload}/>
        {ws.inputs.documents.filter(d => d.role === "company_reference").map(doc => <DocumentRow key={`${doc.id}-${ws.version}`} doc={doc} ws={ws} prefix={prefix} busy={busy} note={note} mutate={mutate}/>)}
        </div></details>
        {ws.inputs.proposal_sections?.some(s=>s.reference && !s.document_kind) && <><details className="border-t pt-3"><summary className="text-sm cursor-pointer">요구사항별 비교 작성 · 기존 방식</summary><ReferenceWriter key={ws.version} ws={ws} prefix={prefix} busy={busy} note={note} mutate={mutate}/></details></>}
        <button className={buttonClass} onClick={() => activateTab(tabs[2])}>서류 확인으로 이동</button>
      </div>
      {tab === tabs[2] && <>
        {!!ws.inputs.form_fillings?.length && <section aria-label="작성된 공고 첨부 양식" className="border-y py-4 space-y-3">
          <h2 className="font-semibold">작성된 공고 첨부 양식</h2>
          <p className="text-sm text-amber-800">원본 서식에 내용을 넣은 검토용 사본입니다. 미작성 항목·근거·한글 문서 배치를 확인하세요.</p>
          {ws.inputs.form_fillings.map(form => <div key={form.document_id} className="flex flex-wrap items-center gap-3 text-sm">
            <span>{ws.inputs.documents.find(doc => doc.id === form.document_id)?.name || "첨부 양식"} · {form.fields.filter(field => field.value.trim()).length}개 항목 작성</span>
            {!ws.source_changed && <a className={buttonClass} href={`/api/v2${prefix}/form-fillings/${encodeURIComponent(form.document_id)}/download`}><Download size={16}/>작성 양식 다운로드</a>}
            <button className={buttonClass} onClick={() => goTo(tabs[1])}>항목별 내용 확인·수정</button>
          </div>)}
        </section>}
        <WorkspacePrerequisites prefix={prefix} version={ws.version} template={template} refreshKey={ws.jobs.filter(j=>["hwp", "hwp_inspect"].includes(j.kind)).map(j=>`${j.id}:${j.status}`).join("|")} onChecked={setPrerequisites} onNavigate={(target, requirementId) => {goTo(tabs[stepIds.indexOf(target)]); setFocusRequirement(requirementId || null);}}/>
        {!ws.inputs.requirements.length && <div role="status" aria-label="요구사항 등록 안내" className="border-l-4 border-amber-500 pl-3 py-2 space-y-2 text-sm"><p>요구사항이 아직 등록되지 않았습니다. 원문 근거를 연결하면 누락 검사를 진행할 수 있습니다.</p><button className={buttonClass} onClick={()=>goTo(tabs[0], "source-requirement-entry")}><ArrowRight size={16}/>원문 기반 요구사항 등록</button></div>}
        <div className="flex flex-wrap gap-2"><button disabled={busy || ws.source_changed || !ws.inputs.requirements.length} className={buttonClass} onClick={() => void run("verify")}><Check size={16}/>누락 검사</button></div>
        <p className="text-sm">요구사항 {ws.inputs.requirements.length}개 · 확인 {ws.inputs.requirements.filter(r => r.review_status === "accepted").length}개</p>
        {ws.proposal_coverage && <p role="status" className="text-sm">제안서 필수 항목 {ws.proposal_coverage.mandatory_count}개 · 본문 대응 {ws.proposal_coverage.covered_count}개 · 별도 증빙 {ws.proposal_coverage.evidence_only_count}개 · 미대응 {ws.proposal_coverage.missing_ids.length}개</p>}
        <CommercialForm key={`commercial-${ws.version}`} ws={ws} busy={busy} prefix={prefix} mutate={mutate}/>
        <div className="grid lg:grid-cols-[240px_minmax(0,1fr)] gap-6 items-start">
          <aside className="min-w-0 lg:sticky lg:top-4 border-y py-3"><h2 className="font-semibold text-sm mb-3">검토할 내용</h2><nav aria-label="초안 항목" className="space-y-2">{[...(ws.inputs.proposal_sections || [])].sort((a,b) => Number(a.review_status === "approved") - Number(b.review_status === "approved")).map(section => <a key={section.id} href={`#section-${section.id}`} className="block text-sm py-2 border-b break-words">{section.title || ws.inputs.requirements.filter(r => section.requirement_ids?.includes(r.id)).map(r => r.text).join(" · ") || "미연결 초안"}<span className={`block text-xs mt-1 ${section.review_status === "approved" ? "text-green-800" : "text-amber-800"}`}>{section.review_status === "approved" ? "내용 승인" : "확인 필요"}</span></a>)}</nav><a href="#generated-files" className="block text-sm underline mt-4">생성 파일 확인</a></aside>
          <div className="min-w-0"><h2 className="font-semibold">제안서 본문 검토</h2>{!ws.inputs.proposal_sections?.length && <p className="py-4 text-sm text-gray-500">작성된 초안이 없습니다. 비교·작성에서 내용을 먼저 저장하세요.</p>}{ws.inputs.proposal_sections?.map(section => <WorkspaceSectionReview key={`${section.id}-${ws.version}`} section={section} ws={ws} prefix={prefix} busy={busy} note={note} mutate={mutate}/>)}</div>
        </div>
      </>}
      {tab === tabs[2] && <>
        <WorkspaceDecision key={`decision-${ws.version}`} ws={ws} prefix={prefix} busy={busy} onSaved={updated => {setWs(updated); setPreview(null);}}/>
        <WorkspaceOutputPlan key={`output-plan-${ws.version}`} ws={ws} prefix={prefix} templates={templates} busy={busy} onSaved={updated => {setWs(updated); setPreview(null);}}/>
        <WorkspaceWorkerStatus/>
        <WorkspaceHwpStatus/>
        <div className="flex flex-wrap gap-2">{["excel", "package"].map(kind => <button key={kind} disabled={busy || ws.source_changed} className={buttonClass} onClick={() => void run(kind)}><Play size={16}/>{jobNames[kind]}</button>)}</div>
        {templateError && <p role="alert" className="text-sm text-red-700">{templateError}</p>}
        <div className="border-y py-3 space-y-3"><div className="flex flex-wrap sm:flex-nowrap gap-2"><select aria-label="HWP 템플릿" className={inputClass} disabled={!templates.length} value={template} onChange={e => {setTemplate(e.target.value); setPreview(null);}}>{templates.map(t => <option key={t.template_key} value={t.template_key}>{t.name}</option>)}</select>
          <button disabled={busy || !templates.length} className={buttonClass} onClick={async () => {try {setPreview(await workspaceApi(`${prefix}/hwp-context?template_key=${template}`));} catch(e) {setStatus((e as Error).message);}}}>입력값 확인</button></div>
          <button disabled={busy || !templates.length || ws.source_changed || ws.jobs.some(j => ["hwp", "hwp_inspect"].includes(j.kind) && ["queued", "running"].includes(j.status))} className={buttonClass} onClick={() => void run("hwp_inspect")}><Check size={16}/>템플릿 필드 검사</button>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={hwpVisible} onChange={e => setHwpVisible(e.target.checked)}/>한글 창 표시</label>
          {preview && <><dl className="grid sm:grid-cols-2 gap-2 text-sm">{Object.entries(preview.values).map(([key,value]) => <div key={key} className="border-b py-2 min-w-0"><dt className="text-gray-500">{key}</dt><dd className="break-words whitespace-pre-wrap">{value || "미입력"}</dd></div>)}</dl><p className="text-amber-800 text-sm">필수 누락 {preview.required_missing.length}개: {preview.required_missing.join(", ") || "없음"}</p></>}
          <button disabled={busy || !preview || !!preview.required_missing.length || preview.input_version !== ws.version || ws.source_changed || !prerequisites?.hwp_request_available || prerequisites.input_version !== ws.version || prerequisites.template_key !== template} className={buttonClass} onClick={() => void run("hwp")}><Play size={16}/>HWP 생성</button>
        </div>
        <ul className="text-sm text-amber-800 list-disc pl-5">{ws.blockers.map(b => <li key={b}>{b}</li>)}</ul>
      </>}
      <details id="generated-files" tabIndex={-1} open={tab !== tabs[0]} className="border-t pt-4 space-y-3 scroll-mt-6"><summary className="font-semibold text-sm cursor-pointer">{tab === tabs[2] ? "생성 서류와 검토 결과" : "분석·작업 이력"}</summary>
        {ws.jobs.length === 0 && <p className="text-sm text-gray-500">실행 기록 없음</p>}
        {ws.jobs.filter(job => (tab === tabs[0] ? ["fetch", "extract", "analyze"] : tab === tabs[1] ? ["extract", "proposal"] : ["verify", "excel", "hwp", "hwp_inspect", "package"]).includes(job.kind)).map(job => <details key={job.id} open={job.input_version === ws.version && ws.jobs.find(j => j.kind === job.kind)?.id === job.id} className="border-b py-3 min-w-0"><summary className="text-sm cursor-pointer"><span className="inline-flex flex-wrap gap-2"><span className="font-medium">{jobNames[job.kind]} · {jobStates[job.status]}</span><span className="text-gray-500">{date(job.created_at)}{job.input_version !== ws.version ? " · 이전 입력" : ""}</span>{job.quality === "warning" && <span className={layoutReviewed(job) ? "text-green-800" : "text-amber-800"}>{layoutReviewed(job) ? "배치 검토 완료" : "경고·검토 필요"}</span>}</span></summary><article className="pt-3 space-y-2 min-w-0">
          <div className="flex flex-wrap justify-between gap-2 text-sm"><strong>{jobNames[job.kind]} · {jobStates[job.status]}</strong><span>버전 {job.input_version}{job.input_version !== ws.version ? " · 이전 입력" : ""} · {date(job.created_at)}</span></div>
          {job.quality === "warning" && <p className="text-xs font-semibold text-amber-800">{layoutReviewed(job) ? "생성 당시 경고 · 배치 검토 완료" : "경고 · 검토 필요"}</p>}
          {job.execution_lane && <p className="text-xs text-gray-500">{job.execution_lane === "local" ? "로컬 문서 실행기" : "외부 연동 실행기"}</p>}
          {job.error?.operation?.failure_stage && <p className="text-sm text-red-700">최초 실패 단계: {job.error.operation.failure_stage} · 현재 단계: {job.error.operation.stage}</p>}
          {!!job.result?.quote_diagnostics?.length && <QuoteRecovery job={job} ws={ws} prefix={prefix} reload={reload}/>}
          {job.error && <><p className="text-sm text-red-700 break-words">{readableError(job.error.message)} {readableError(job.error.next_action)}</p><details className="text-xs text-gray-500"><summary>기술 상세</summary><p className="break-all">{job.error.code} · {job.error.message}</p></details></>}
          {job.result?.warnings?.map((warning,i) => <p className="text-sm text-amber-800 break-words" key={i}>{layoutReviewed(job) && warning === "한글 페이지 배치는 담당자 검토가 필요합니다." ? "생성 당시 배치 검토 요청 · 현재 파일 검토 완료" : warning}</p>)}
          {job.result?.remaining_placeholders && <p className="text-sm">미입력 항목: {job.result.remaining_placeholders.join(", ") || "없음"}</p>}
          {job.result?.required_missing && <p className="text-sm">필수 누락: {job.result.required_missing.join(", ") || "없음"}</p>}
          {job.kind === "hwp" && job.result?.artifact && <p className="text-sm">저장값 재조회: {job.result.verified ? layoutReviewed(job) ? "일치 확인 · 문서 배치 검토 완료" : "일치 확인 · 문서 배치 검토 필요" : "미확인"}</p>}
          {job.kind === "hwp_inspect" && job.result && <p className="text-sm">실제 필드 {job.result.fields?.length || 0}개 · {job.result.inspection_passed ? "필수 필드 확인" : "필드 보완 필요"} · 미매핑 {(job.result.unmapped || []).join(", ") || "없음"}</p>}
          {job.result?.axes && <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left border-b"><th className="py-2">검토 축</th><th>결과</th><th>판단 근거</th></tr></thead><tbody>{Object.entries(job.result.axes).map(([axis,value]) => <tr key={axis} className="border-b align-top"><th className="py-2 pr-3 whitespace-nowrap text-left">{{spec: "기술 규격", qualification: "참가 자격", price: "기초금액 대비"}[axis] || axis}</th><td className="py-2 pr-3 whitespace-nowrap">{value.score == null ? "미평가" : `${Math.round(value.score * 100)}%`}</td><td className="py-2 min-w-48">{value.reason}</td></tr>)}</tbody></table><p className="text-sm mt-2">종합: {job.result.score_total == null ? "미평가" : `${Math.round(job.result.score_total * 100)}%`} · 기술 근거 확인율: {job.result.technical_coverage == null ? "미확인" : `${Math.round(job.result.technical_coverage * 100)}%`}</p></div>}
          {job.result?.candidates?.map(candidate => <p key={candidate.sku.sku_id} className="text-sm break-words">SKU 참고 · {candidate.sku.name || candidate.sku.sku_id} · 검색 유사도 {Math.round(candidate.similarity * 100)}% · 적합성 확인 대기</p>)}
          {job.result?.qualification_references && <div className="text-sm"><p>{job.result.qualification_references.reason}</p>{job.result.qualification_references.references && <dl className="space-y-1 mt-2">{Object.entries(job.result.qualification_references.references).map(([key,values]) => <div key={key}><dt className="font-medium">{{licenses: "면허", regions: "지역", permitted_industries: "업종"}[key] || key}</dt><dd>{values.join(", ") || "조회 항목 없음"}</dd></div>)}</dl>}</div>}
          {job.result?.sections?.map((s,i) => <p key={i} className="text-sm whitespace-pre-wrap">{s.text}</p>)}
          <div className="flex flex-wrap gap-2">
            {job.status === "succeeded" && job.input_version === ws.version && ["fetch", "extract", "analyze", "proposal"].includes(job.kind) && <button disabled={busy || ws.source_changed} className={buttonClass} onClick={() => void mutate(`${prefix}/jobs/${job.id}/apply`, {version: ws.version}, "검토 대상으로 반영 완료")}><Check size={16}/>결과 반영</button>}
            {job.result?.artifact && job.status === "succeeded" && <><a className={buttonClass} href={`/api/v2/jobs/${job.id}/download`}><Download size={16}/>다운로드</a>
              <WorkspaceArtifactReview key={`${job.id}-${ws.version}-${job.result.sha256}-${ws.reviews.find(r => r.job_id === job.id)?.id || "pending"}`} job={job} version={ws.version} sourceChanged={ws.source_changed} busy={busy}
                note={reviewNotes[job.id] ?? note} onNote={value => setReviewNotes({...reviewNotes, [job.id]: value})}
                onReview={(action, proof) => void mutate(`${prefix}/reviews`, {version: ws.version, job_id: job.id, action, note: reviewNotes[job.id] ?? note,
                  expected_review_id: ws.reviews.find(r => r.job_id === job.id)?.id || null, ...proof}, "검토 기록 저장")}/></>}
          </div>
          {!['queued', 'running'].includes(job.status) && (job.status !== 'succeeded' || ['excel', 'hwp', 'package'].includes(job.kind)) && <div className="flex flex-wrap gap-2 items-center">
            {["hwp", "hwp_inspect"].includes(job.kind) && <label className="text-sm flex gap-2"><input type="checkbox" checked={!!recoveryConfirmed[job.id]} onChange={e => setRecoveryConfirmed({...recoveryConfirmed, [job.id]: e.target.checked})}/>Worker 종료·기존 파일 확인</label>}
            <button className={buttonClass} disabled={busy || !note.trim() || ws.source_changed || (["hwp", "hwp_inspect"].includes(job.kind) && !recoveryConfirmed[job.id])} onClick={() => void mutate(`/jobs/${job.id}/recover`, {version: ws.version, idempotency_key: crypto.randomUUID(), note, external_state_confirmed: !!recoveryConfirmed[job.id], visible: hwpVisible}, "현재 입력으로 복구 작업 접수")}><RefreshCw size={16}/>복구·재생성</button>
          </div>}
          {job.parameters?.recovery_of && <p className="text-xs text-gray-500">이전 작업 복구: {job.parameters.recovery_of}</p>}
          {!!job.result?.pages?.length && <details className="w-full"><summary className="cursor-pointer text-sm">한글 페이지 미리보기 · {job.result.pages.length}쪽 · {layoutReviewed(job) ? "배치 검토 완료" : "배치 검토 필요"}</summary><div className="grid gap-3 sm:grid-cols-2 mt-3">{job.result.pages.map(page => <a key={page.number} href={`/api/v2/jobs/${job.id}/pages/${page.number}`} target="_blank" rel="noreferrer" aria-label={`${page.number}쪽 크게 보기`}><img src={`/api/v2/jobs/${job.id}/pages/${page.number}`} alt={`생성 HWP ${page.number}쪽`} loading="lazy" width={page.width} height={page.height} className="w-full h-auto border"/></a>)}</div></details>}
          <p className="text-sm">검토 상태: {({approved: "승인", rejected: "반려", ready: "제출 준비 확인", recovery_requested: "복구 요청"} as Record<string, string>)[ws.reviews.find(r => r.job_id === job.id)?.action || ""] || "검토 대기"}{job.input_version !== ws.version ? " · 이전 입력 기준" : ""}</p>
          <p className="text-xs text-gray-500">{ws.reviews.find(r => r.job_id === job.id)?.note || ""}</p>
          {ws.reviews.some(r => r.job_id === job.id) && <p className="text-xs text-gray-500">기록 담당자: {actorLabel(ws.reviews.find(r => r.job_id === job.id)?.actor)}</p>}
        </article></details>)}
      </details>
      <details><summary className="text-sm">변경·검토 이력</summary>{ws.reviews.map(r => <div className="border-t pt-2 text-sm" key={r.id}><strong>버전 {r.input_version}</strong> · {date(r.created_at)}<p>{r.note}</p><p className="text-xs text-gray-500">{actorLabel(r.actor)}</p></div>)}</details>
      </section>
    </>}
  </div>;
}

type Mutate = (path: string, body: unknown, message?: string) => Promise<void>;

function ReferenceWriter({ws, prefix, busy, note, mutate}: {ws: Workspace; prefix: string; busy: boolean; note: string; mutate: Mutate}) {
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

function officialAttachmentUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) &&
      ["www.g2b.go.kr", "g2b.go.kr"].includes(url.hostname) &&
      !url.username && !url.password && !url.port ? url.href : null;
  } catch { return null; }
}

function SourceInventory({attachments, pendingIndexes = []}: {attachments: SourceAttachment[]; pendingIndexes?: number[]}) {
  const states = {missing: "파일 미확보", unread: "본문 미확인", ready: "본문 확보"};
  return <div className="min-w-0 space-y-2">
    <h2 className="text-base font-semibold">나라장터 첨부 목록</h2>
    <p className="text-sm">목록 {attachments.length}개 · 파일 연결 {attachments.filter(a => a.document_ids.length > 0).length}개 · 본문 확보 {attachments.filter(a => a.state === "ready").length}개</p>
    <table aria-label="나라장터 첨부 목록" className="w-full table-fixed text-sm">
      <thead className="text-left border-b"><tr><th scope="col" className="w-10 py-2">번호</th><th scope="col" className="py-2">파일명</th><th scope="col" className="w-28 py-2 pl-2">확보 상태</th></tr></thead>
      <tbody>{attachments.map(attachment => {
        const url = officialAttachmentUrl(attachment.url);
        return <tr key={attachment.index} className="border-b align-top">
          <td className="py-2">{attachment.index}</td>
          <td className="py-2"><div className="flex items-start gap-2 min-w-0"><span className="min-w-0 break-all">{attachment.name}</span>{url && <a href={url} target="_blank" rel="noopener noreferrer" className="shrink-0 p-1" aria-label={`${attachment.name} 나라장터 원본 열기`} title="나라장터 원본 열기"><Download size={16}/></a>}</div></td>
          <td className="py-2 pl-2">{attachment.state === "missing" && pendingIndexes.includes(attachment.index) ? "다운로드 완료 · 반영 대기" : states[attachment.state]}</td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}

function DocumentRow({doc, ws, prefix, busy, note, mutate}: {doc: SourceDocument; ws: Workspace; prefix: string; busy: boolean; note: string; mutate: Mutate}) {
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

const archiveIssues: Record<string, string> = {
  archive_depth_limit: "중첩 ZIP 깊이 초과 · 개별 파일로 등록하세요",
  hwp_worker_required: "HWP 실행기 연결 필요", hwp_worker_auth_missing: "HWP 실행기 인증 설정 필요",
  hwp_worker_unavailable: "HWP 실행기 연결 확인 필요", hwp_member_limit: "HWP 처리 개수 초과 · 나누어 등록하세요",
  member_format_mismatch: "확장자와 실제 파일 형식 불일치", unsupported_member_format: "미지원 형식 · 변환본 필요",
  hwp_member_storage_unsafe: "HWP 임시 저장 경로 확인 필요", hwp_member_source_changed: "HWP 원본 변경 · 다시 등록하세요",
};

const ocrIssues: Record<string, string> = {
  ocr_engine_missing: "OCR 프로그램 설치 필요", ocr_engine_unavailable: "OCR 프로그램 실행 확인 필요",
  ocr_configuration_invalid: "OCR 설정 확인 필요", ocr_failed: "OCR 실패 · 원본 또는 변환본 확인 필요",
  ocr_timeout: "OCR 시간 초과 · 페이지를 나누어 등록하세요", ocr_page_limit: "OCR 페이지 한도 초과 · 나누어 등록하세요",
  ocr_disabled: "OCR 기능 설정 필요", ocr_output_limit: "OCR 결과 크기 초과 · 나누어 등록하세요",
  ocr_language_missing: "OCR 언어 파일 설치 필요",
};

function ExtractionPages({pages}: {pages: ExtractedPage[]}) {
  return <>{pages.map(page => <div key={page.page_no}>
    <p>{page.page_no}쪽 · {page.status === "unread" ? "본문 미확보 · OCR 설정 또는 변환본 확인" : page.review_required ? "OCR 본문 · 원문 대조 필요" : "텍스트 확보"}{page.confidence != null ? ` · OCR 신뢰도 ${page.confidence}%` : ""}</p>
    {page.code && ocrIssues[page.code] && <p className="text-amber-800">{ocrIssues[page.code]}{page.missing_languages?.length ? `: ${page.missing_languages.map(language => ({kor: "한국어", eng: "영어", chi_tra: "번체 중국어"} as Record<string, string>)[language] || language).join(", ")}` : ""}</p>}
  </div>)}</>;
}

function ArchiveMembers({members}: {members: ExtractedArchiveMember[]}) {
  return <ul className="space-y-1 pl-3 border-l mt-2">{members.map(member => <li key={member.name} className="break-all">
    <p>{member.name} · {member.complete ? "본문 확보" : member.status === "unsupported" ? "미지원 형식 · 변환본 필요" : "본문 확인 필요"}</p>
    {member.error_code && <p className="text-amber-800">{archiveIssues[member.error_code] || "추출 오류 · 원본 파일 확인 필요"}</p>}
    {member.extraction?.pages && <ExtractionPages pages={member.extraction.pages}/>}
    {!!member.extraction?.members?.length && <ArchiveMembers members={member.extraction.members}/>}
  </li>)}</ul>;
}

function RequirementForm({req, ws, prefix, busy, mutate}: {req?: Requirement; ws: Workspace; prefix: string; busy: boolean; mutate: Mutate}) {
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

function CommercialForm({ws, prefix, busy, mutate}: {ws: Workspace; prefix: string; busy: boolean; mutate: Mutate}) {
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
