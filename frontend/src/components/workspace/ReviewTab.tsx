import { ArrowRight, Check, Download, Play } from "lucide-react";
import { jobNames, workspaceApi, type Workspace } from "@/lib/workspace";
import WorkspacePrerequisites, { type Prerequisites } from "../WorkspacePrerequisites";
import WorkspaceSectionReview from "../WorkspaceSectionReview";
import WorkspaceDecision from "../WorkspaceDecision";
import WorkspaceOutputPlan from "../WorkspaceOutputPlan";
import WorkspaceWorkerStatus from "../WorkspaceWorkerStatus";
import WorkspaceHwpStatus from "../WorkspaceHwpStatus";
import CommercialForm from "./CommercialForm";
import { inputClass, buttonClass, tabs, stepIds, type Mutate, type Tab } from "./ui";

export type HwpPreview = {input_version: number; values: Record<string, string>; required_missing: string[]};
interface Props {ws: Workspace; tab: Tab; prefix: string; busy: boolean; note: string; mutate: Mutate; run: (kind: string) => Promise<void>; goTo: (name: Tab, target?: string) => void;
  setWs: (ws: Workspace) => void; setStatus: (message: string) => void; setFocusRequirement: (id: string | null) => void;
  template: string; setTemplate: (key: string) => void; templates: {template_key: string; name: string}[]; templateError: string;
  hwpVisible: boolean; setHwpVisible: (value: boolean) => void; preview: HwpPreview | null; setPreview: (value: HwpPreview | null) => void;
  prerequisites: Prerequisites | null; setPrerequisites: (value: Prerequisites | null) => void}

/** Tab "4. 서류 확인": filled forms, prerequisites, section review, decision and output generation. */
export default function ReviewTab({ws, tab, prefix, busy, note, mutate, run, goTo, setWs, setStatus, setFocusRequirement, template, setTemplate, templates, templateError, hwpVisible, setHwpVisible, preview, setPreview, prerequisites, setPrerequisites}: Props) {
  return <>
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
  </>;
}
