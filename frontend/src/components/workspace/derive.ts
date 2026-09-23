import { jobNames, jobStates, Workspace, WorkspaceJob } from "@/lib/workspace";
import { Tab, tabs } from "./ui";
import { hasAttachmentOnlyPlan } from "./outputPlan";
import {templateProvenanceWarning} from "@/lib/templateProvenance";

/** Values derived from a workspace snapshot. Pure: no React, no I/O (R6). */
export function deriveWorkspace(ws: Workspace | null) {
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
  return {hwpBlocked, hwpMissing, needsSourceReview, sourceDocuments, hasSourceText, pendingFetch, pendingExtract, activeJob, unreadSource, missingAttachment};
}
export type Derived = ReturnType<typeof deriveWorkspace>;

/** A generated HWP whose current file has an approved layout review. */
export function layoutReviewed(ws: Workspace | null, job: WorkspaceJob): boolean {
  const review = ws?.reviews.find(r => r.job_id === job.id);
  return !!(job.kind === "hwp" && job.input_version === ws?.version && review?.action === "approved"
    && review.layout_confirmed && review.output_sha256 === job.result?.sha256
    && !templateProvenanceWarning(job.result?.template_provenance, job.parameters?.template_key || job.result?.template_key));
}

/** What the primary "지금 할 작업" button does, as data so the decision stays testable. */
export type NextAction =
  | {type: "mutate"; path: string; body: unknown; message: string}
  | {type: "run"; kind: string}
  | {type: "goto"; tab: Tab; target?: string};

export interface NextStep {
  title: string;
  label: string;
  disabled?: boolean;
  href?: string;
  action?: NextAction;
}

/** The single next action for the workspace, in priority order. */
export function nextStep(ws: Workspace | null, prefix: string, d: Derived): NextStep | null {
  if (!ws) return null;
  if (d.activeJob) return {title: `${jobNames[d.activeJob.kind]} · ${jobStates[d.activeJob.status]}`, label: "처리 중", disabled: true};
  if (ws.source_changed) return {title: "공고 원문이 변경되었습니다", label: "최신 원문 동기화", action: {type: "mutate", path: `${prefix}/sync`, body: {version: ws.version}, message: "원문 동기화 완료"}};
  if (d.pendingFetch) return {title: "첨부 다운로드 완료 · 검토 자료에 반영 대기", label: "다운로드한 첨부 반영", action: {type: "mutate", path: `${prefix}/jobs/${d.pendingFetch.id}/apply`, body: {version: ws.version}, message: "첨부 반영 완료 · 본문 추출이 필요합니다."}};
  if (d.missingAttachment || !d.sourceDocuments.length) {
    const downloadable = ws.source_attachments?.some(a => a.state === "missing" && a.url.trim());
    const fetch = ws.jobs.find(j => j.kind === "fetch" && j.input_version === ws.version);
    const failed = fetch && ["failed", "blocked"].includes(fetch.status);
    if (!downloadable || failed) return {title: failed ? "첨부를 가져오지 못했습니다. 원문 파일을 등록하세요" : "검토할 공고 원문 파일을 등록하세요", label: "공고 원문 등록", action: {type: "goto", tab: tabs[0], target: "source-upload-file"}};
    return {title: "검토할 공고 원문이 필요합니다", label: "누락 첨부 가져오기", action: {type: "run", kind: "fetch"}};
  }
  if (d.pendingExtract) return {title: "본문 추출 완료 · 분석 입력에 반영 대기", label: "추출한 본문 반영", action: {type: "mutate", path: `${prefix}/jobs/${d.pendingExtract.id}/apply`, body: {version: ws.version}, message: "본문 반영 완료"}};
  if (!d.hasSourceText || d.unreadSource) return {title: "첨부 파일의 본문을 읽어야 합니다", label: "원문 본문 추출", action: {type: "run", kind: "extract"}};
  if (ws.writing_plan_current) {
    const missing = ws.inputs.writing_plan?.items.filter(item => item.action === "write" && !ws.inputs.proposal_sections?.some(s => s.id === item.id && s.text.trim())) || [];
    if (missing.length) return {title: `공고에서 확인한 작성 항목 ${missing.length}개가 남았습니다`, label: "비교·작성", action: {type: "goto", tab: tabs[1]}};
  }
  if (!ws.inputs.requirements.length) return {title: "제출서류와 주요 사항을 확인하세요", label: "공고 핵심 확인", action: {type: "goto", tab: tabs[0], target: "notice-brief"}};
  if (d.hwpMissing) return {title: "HWP 필수 입력값 확인이 필요합니다", label: "회사정보 확인", href: "/admin#company"};
  if (d.hwpBlocked) return {title: "HWP 생성 차단 사유를 확인하세요", label: "생성 결과 확인", action: {type: "goto", tab: tabs[2], target: "generated-files"}};
  if (d.needsSourceReview) return {title: "제출서류와 주요 사항을 확인하세요", label: "공고 핵심 확인", action: {type: "goto", tab: tabs[0], target: "notice-brief"}};
  const noWriting = hasAttachmentOnlyPlan(ws);
  if (!ws.inputs.proposal_sections?.length && !noWriting) return {title: "기존 작성자료와 비교해 초안을 작성하세요", label: "비교·작성", action: {type: "goto", tab: tabs[1]}};
  if (ws.ready) return {title: "제출 준비 확인 완료", label: "최종 패키지 확인", action: {type: "goto", tab: tabs[2], target: "generated-files"}};
  return {title: ws.next_action, label: "서류 확인", action: {type: "goto", tab: tabs[2]}};
}
