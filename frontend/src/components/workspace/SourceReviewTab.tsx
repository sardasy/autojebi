import { Check, Download, FileText, Play, Upload } from "lucide-react";
import { type Workspace } from "@/lib/workspace";
import JevClassification from "./JevClassification";
import NoticeBrief from "../NoticeBrief";
import WritingPlanReview from "../WritingPlanReview";
import WorkspaceDocumentViewer from "../WorkspaceDocumentViewer";
import WorkspaceRequirementCandidates from "../WorkspaceRequirementCandidates";
import SourceDisplayReview from "../SourceDisplayReview";
import CompanyAssets from "../CompanyAssets";
import { SourceNeeds } from "../WorkspaceRecovery";
import SourceInventory from "./SourceInventory";
import DocumentRow from "./DocumentRow";
import RequirementForm from "./RequirementForm";
import { inputClass, buttonClass, tabs, type Mutate, type Tab } from "./ui";
import type { Derived } from "./derive";
interface Props {ws: Workspace; prefix: string; noticeNo: string; busy: boolean; note: string; derived: Derived;
  mutate: Mutate; run: (kind: string) => Promise<void>; reload: () => Promise<boolean>; setWs: (ws: Workspace) => void; goTo: (name: Tab, target?: string) => void; activateTab: (name: Tab) => void}

/** Tab "2. 공고 서류 검토": source files, extraction state and requirements. */
export default function SourceReviewTab({ws, prefix, noticeNo, busy, note, derived: {sourceDocuments, hasSourceText, pendingFetch, pendingExtract}, mutate, run, reload, setWs, goTo, activateTab}: Props) {
  return <>
        <JevClassification ws={ws} prefix={prefix} busy={busy} mutate={mutate}/>
        {hasSourceText && <NoticeBrief documents={ws.inputs.documents} prefix={prefix} serverBrief={ws.notice_brief}/>}
        {hasSourceText && <SourceDisplayReview key={`display-${ws.version}`} ws={ws} prefix={prefix} onSaved={setWs}/>}
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
          <label className="text-sm min-w-0">파일<input id="source-upload-file" name="file" type="file" required className="block max-w-full"/></label><button disabled={busy} className={buttonClass}><Upload size={16}/>등록</button>
        </form>
        <CompanyAssets noticeNo={noticeNo} version={ws.version} onLinked={reload}/>
        {ws.inputs.documents.filter(doc => doc.role !== "company_reference").map(doc => <DocumentRow key={`${doc.id}-${ws.version}`} doc={doc} ws={ws} prefix={prefix} busy={busy} note={note} mutate={mutate}/>)}
        {!sourceDocuments.length && !ws.inputs.requirements.length && <details id="source-requirement-entry" className="py-3"><summary className="text-sm cursor-pointer">원문 요구사항 수동 등록</summary><RequirementForm ws={ws} busy={busy} prefix={prefix} mutate={mutate}/></details>}
        </details>
        <button className={buttonClass} onClick={() => activateTab(tabs[1])}>비교·작성으로 이동</button>
        </div></details>
  </>;
}
