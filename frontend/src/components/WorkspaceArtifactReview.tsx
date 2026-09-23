"use client";

import {useState} from "react";
import {Check, X} from "lucide-react";
import {WorkspaceJob} from "@/lib/workspace";
import {templateProvenanceWarning} from "@/lib/templateProvenance";

export type ArtifactReviewAction = "approved" | "rejected" | "ready";
const button = "inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 border rounded px-3 py-2 text-sm disabled:opacity-40";

export default function WorkspaceArtifactReview({job, version, sourceChanged, busy, note, onNote, onReview}: {
  job: WorkspaceJob; version: number; sourceChanged: boolean; busy: boolean; note: string;
  onNote: (value: string) => void;
  onReview: (action: ArtifactReviewAction, proof: {output_sha256?: string; layout_confirmed: boolean}) => void;
}) {
  const [layoutConfirmed, setLayoutConfirmed] = useState(false);
  const result = job.result;
  const hwp = job.kind === "hwp";
  const provenanceIssue = hwp ? templateProvenanceWarning(result?.template_provenance, job.parameters?.template_key || result?.template_key) : null;
  const incomplete = hwp && (!result?.verified || !/^[a-f0-9]{64}$/i.test(result.sha256 || "") ||
    !!result.required_missing?.length || !!result.missing?.length || !!result.remaining_placeholders?.length);
  const disabled = busy || sourceChanged || job.input_version !== version || !note.trim();
  return <div className="w-full space-y-2">
    {hwp && <label className="flex items-start gap-2 text-sm">
      <input type="checkbox" checked={layoutConfirmed} disabled={busy || job.input_version !== version || sourceChanged} onChange={event => setLayoutConfirmed(event.target.checked)}/>
      생성된 한글 파일의 내용·표·줄바꿈·쪽 나눔을 확인했습니다
    </label>}
    {incomplete && <p className="text-sm text-amber-800">저장값 검증과 미입력 항목을 해결한 뒤 파일을 승인할 수 있습니다.</p>}
    {provenanceIssue && <p className="text-sm text-amber-800">{provenanceIssue}</p>}
    <label className="block text-sm">파일 검토 의견<input aria-label="파일 검토 의견" className="mt-1 block w-full min-w-0 rounded border border-gray-300 bg-white p-2 text-sm" value={note} maxLength={2000} disabled={busy} onChange={event => onNote(event.target.value)}/></label>
    <div className="flex flex-wrap gap-2">
      {(["approved", "rejected", ...(job.kind === "package" ? ["ready"] : [])] as ArtifactReviewAction[]).map(action => <button key={action}
        disabled={disabled || (action === "approved" && (!!provenanceIssue || incomplete || (hwp && !layoutConfirmed)))} className={button}
        onClick={() => {onReview(action, {output_sha256: result?.sha256, layout_confirmed: hwp && layoutConfirmed}); setLayoutConfirmed(false);}}>
        {action === "rejected" ? <X size={16}/> : <Check size={16}/>}
        {{approved: "초안 승인", rejected: "반려", ready: "제출 준비 확인"}[action]}
      </button>)}
    </div>
  </div>;
}
