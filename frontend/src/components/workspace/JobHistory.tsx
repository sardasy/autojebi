import { Check, Download, RefreshCw } from "lucide-react";
import { jobNames, jobStates, type Workspace, type WorkspaceJob } from "@/lib/workspace";
import WorkspaceArtifactReview from "../WorkspaceArtifactReview";
import TemplateProvenanceNotice from "../TemplateProvenanceNotice";
import { QuoteRecovery } from "../WorkspaceRecovery";
import { buttonClass, tabs, readableError, actorLabel, date, type Mutate, type Tab } from "./ui";
import { layoutReviewed as isLayoutReviewed } from "./derive";
import { applyResultMessage } from "@/lib/requirementDuplicates";
interface Props {ws: Workspace; tab: Tab; prefix: string; busy: boolean; note: string; mutate: Mutate; reload: () => Promise<boolean>;
  hwpVisible: boolean; reviewNotes: Record<string, string>; setReviewNotes: (value: Record<string, string>) => void;
  recoveryConfirmed: Record<string, boolean>; setRecoveryConfirmed: (value: Record<string, boolean>) => void}

/** Job history for the active tab: results, warnings, downloads, artifact review and recovery. */
export default function JobHistory({ws, tab, prefix, busy, note, mutate, reload, hwpVisible, reviewNotes, setReviewNotes, recoveryConfirmed, setRecoveryConfirmed}: Props) {
  const layoutReviewed = (job: WorkspaceJob) => isLayoutReviewed(ws, job);
  return (
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
          {job.kind === "hwp_inspect" && <TemplateProvenanceNotice value={job.result?.template_provenance} templateKey={job.parameters?.template_key}/>}
          {job.result?.axes && <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left border-b"><th className="py-2">검토 축</th><th>결과</th><th>판단 근거</th></tr></thead><tbody>{Object.entries(job.result.axes).map(([axis,value]) => <tr key={axis} className="border-b align-top"><th className="py-2 pr-3 whitespace-nowrap text-left">{{spec: "기술 규격", qualification: "참가 자격", price: "기초금액 대비"}[axis] || axis}</th><td className="py-2 pr-3 whitespace-nowrap">{value.score == null ? "미평가" : `${Math.round(value.score * 100)}%`}</td><td className="py-2 min-w-48">{value.reason}</td></tr>)}</tbody></table><p className="text-sm mt-2">종합: {job.result.score_total == null ? "미평가" : `${Math.round(job.result.score_total * 100)}%`} · 기술 근거 확인율: {job.result.technical_coverage == null ? "미확인" : `${Math.round(job.result.technical_coverage * 100)}%`}</p></div>}
          {job.result?.candidates?.map(candidate => <p key={candidate.sku.sku_id} className="text-sm break-words">SKU 참고 · {candidate.sku.name || candidate.sku.sku_id} · 검색 유사도 {Math.round(candidate.similarity * 100)}% · 적합성 확인 대기</p>)}
          {job.result?.qualification_references && <div className="text-sm"><p>{job.result.qualification_references.reason}</p>{job.result.qualification_references.references && <dl className="space-y-1 mt-2">{Object.entries(job.result.qualification_references.references).map(([key,values]) => <div key={key}><dt className="font-medium">{{licenses: "면허", regions: "지역", permitted_industries: "업종"}[key] || key}</dt><dd>{values.join(", ") || "조회 항목 없음"}</dd></div>)}</dl>}</div>}
          {job.result?.sections?.map((s,i) => <p key={i} className="text-sm whitespace-pre-wrap">{s.text}</p>)}
          <div className="flex flex-wrap gap-2">
            {job.status === "succeeded" && job.input_version === ws.version && ["fetch", "extract", "analyze", "proposal"].includes(job.kind) && <button disabled={busy || ws.source_changed} className={buttonClass} onClick={() => void mutate(`${prefix}/jobs/${job.id}/apply`, {version: ws.version}, job.kind === "analyze" ? applyResultMessage(ws.inputs.requirements, job.result?.requirements) : "검토 대상으로 반영 완료")}><Check size={16}/>결과 반영</button>}
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
  );
}
