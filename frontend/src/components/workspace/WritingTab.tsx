import { FileText, Upload } from "lucide-react";
import { type Workspace } from "@/lib/workspace";
import CompanyAssets from "../CompanyAssets";
import NoticeFormWorkspace from "../NoticeFormWorkspace";
import SpecificationWorkbench from "../SpecificationWorkbench";
import DocumentWritingWorkspace, { type SelectedWritingEvidence } from "../DocumentWritingWorkspace";
import DocumentRow from "./DocumentRow";
import ReferenceWriter from "./ReferenceWriter";
import { buttonClass, tabs, type Mutate, type Tab } from "./ui";

interface Props {ws: Workspace; tab: Tab; prefix: string; noticeNo: string; busy: boolean; note: string;
  picked: (SelectedWritingEvidence & {noticeNo: string}) | null; setPicked: (value: (SelectedWritingEvidence & {noticeNo: string}) | null) => void;
  setWs: (ws: Workspace) => void; setPreview: (value: null) => void; mutate: Mutate; run: (kind: string) => Promise<void>; reload: () => Promise<boolean>; goTo: (name: Tab, target?: string) => void; activateTab: (name: Tab) => void}

/** Tab "3. 비교·작성": original forms, specification search and document drafting. Stays mounted (hidden) to keep drafts. */
export default function WritingTab({ws, tab, prefix, noticeNo, busy, note, picked, setPicked, setWs, setPreview, mutate, run, reload, goTo, activateTab}: Props) {
  return (
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
  );
}
