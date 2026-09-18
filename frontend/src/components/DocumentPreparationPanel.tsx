"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Upload, FolderOpen } from "lucide-react";

import {
  actionAnalyzeDocuments,
  actionFetchG2BAttachments,
  actionReviewHwpJob,
  actionUpdateDocumentChecklistItem,
  actionValidateDocuments,
} from "@/lib/actions";
import type {
  DocumentChecklistItem,
  HwpJobRecord,
  DocumentItemStatus,
  NoticeRecord,
  ExportRecord,
} from "@/lib/api";
import {
  documentSummaryText,
  readDocumentAutomation,
} from "@/lib/documentAutomation";
import { CommonDocumentsDialog } from "./CommonDocumentsDialog";
import { ExportButtonGroup } from "./ExportButtonGroup";
import { SpecItemsPanel } from "./SpecItemsPanel";
import { UploadDocumentDialog } from "./UploadDocumentDialog";
import { UploadsTable } from "./UploadsTable";
import { useToast } from "./Toast";

type Props = {
  notice: NoticeRecord;
  view?: "all" | "documents";
};

const STATUS_OPTIONS: DocumentItemStatus[] = [
  "needed",
  "ready",
  "generated",
  "blocked",
  "not_applicable",
];

const STATUS_LABEL: Record<DocumentItemStatus, string> = {
  needed: "필요",
  ready: "준비완료",
  generated: "초안생성",
  blocked: "막힘",
  not_applicable: "해당없음",
};

export function DocumentPreparationPanel({ notice, view = "all" }: Props) {
  const [pending, startTransition] = useTransition();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [commonOpen, setCommonOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<string | undefined>();
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const toast = useToast();
  const router = useRouter();
  const docs = useMemo(() => readDocumentAutomation(notice), [notice]);
  const canAnalyze = notice.status !== "collected";
  const uploads = docs?.uploads || [];
  const exports = docs?.exports || [];
  const hwpJobs = docs?.hwp_jobs || [];

  const analyze = () => {
    setResultMessage("서류 분석 중입니다.");
    startTransition(async () => {
      try {
        const r = await actionAnalyzeDocuments(notice.notice_no);
        const message = `서류 분석 완료: ${r.document_automation.checklist.length}개 항목`;
        setResultMessage(message);
        toast.push("success", message);
        router.refresh();
      } catch (e) {
        const message = `서류 분석 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  const fetchAttachments = () => {
    setResultMessage("G2B 첨부 서류를 가져오는 중입니다.");
    startTransition(async () => {
      try {
        const r = await actionFetchG2BAttachments(notice.notice_no);
        const suffix =
          r.errors.length > 0 ? ` · 오류 ${r.errors.length}건 기록` : "";
        const message = `첨부 서류 가져오기 완료: ${r.fetched.length}개${suffix}`;
        setResultMessage(message);
        toast.push(r.fetched.length > 0 ? "success" : "info", message);
        router.refresh();
      } catch (e) {
        const message = `첨부 서류 가져오기 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  const validate = () => {
    setResultMessage("제출 전 검증 중입니다.");
    startTransition(async () => {
      try {
        const r = await actionValidateDocuments(notice.notice_no);
        if (r.ready_for_submission) {
          const message = "제출 전 검증 통과: 필수 누락 항목이 없습니다.";
          setResultMessage(message);
          toast.push("success", message);
        } else {
          const message = `필수 누락 ${r.missing_required.length}건: ${r.missing_required
            .map((item) => item.name)
            .join(", ")}`;
          setResultMessage(message);
          toast.push("info", message);
        }
        router.refresh();
      } catch (e) {
        const message = `검증 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  const updateStatus = (item: DocumentChecklistItem, status: DocumentItemStatus) => {
    startTransition(async () => {
      try {
        await actionUpdateDocumentChecklistItem(notice.notice_no, item.id, { status });
        const message = `${item.name}: ${STATUS_LABEL[status]} 저장`;
        setResultMessage(message);
        toast.push("success", message);
        router.refresh();
      } catch (e) {
        const message = `상태 저장 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-700">서류 준비</h2>
          {docs ? (
            <p className="mt-1 text-xs text-slate-500">
              {documentSummaryText(docs)}
            </p>
          ) : (
            <p className="mt-1 text-xs text-slate-500">
              분석 후 체크리스트와 검토용 초안을 생성합니다.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={fetchAttachments}
            disabled={pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            첨부 서류 가져오기
          </button>
          <button
            type="button"
            onClick={analyze}
            disabled={!canAnalyze || pending}
            className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-600"
          >
            서류 분석
          </button>
          <button
            type="button"
            onClick={() => { setSelectedItem(undefined); setUploadOpen(true); }}
            disabled={!docs || pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            파일 업로드
          </button>
          <button
            type="button"
            onClick={() => { setSelectedItem(undefined); setCommonOpen(true); }}
            disabled={!docs || pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            공통 서류 가져오기
          </button>
          <button
            type="button"
            onClick={validate}
            disabled={!docs || pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            제출 전 검증
          </button>
        </div>
      </div>

      {resultMessage ? (
        <div role="status" className="rounded border border-slate-300 bg-slate-50/70 p-3 text-sm text-slate-900">
          {resultMessage}
        </div>
      ) : null}

      {docs ? (
        <>
          <DocumentErrors errors={docs.errors} />
          <RemainingPlaceholders drafts={docs.drafts} />
          {view === "all" && <HwpJobs noticeNo={notice.notice_no} jobs={hwpJobs} exports={exports} />}
          {view === "all" && <SpecItemsPanel notice={notice} enabled={Boolean(docs)} />}
          <ChecklistTable
            items={[...docs.checklist].sort((a,b) => Number(b.required && !["ready","generated","not_applicable"].includes(b.status)) - Number(a.required && !["ready","generated","not_applicable"].includes(a.status)))}
            pending={pending}
            onStatusChange={updateStatus}
            onUpload={item => { setSelectedItem(item.id); setUploadOpen(true); }}
            onCommon={item => { setSelectedItem(item.id); setCommonOpen(true); }}
          />
          <Risks risks={docs.risks} />
          <details><summary className="cursor-pointer text-sm">초안 및 입력값</summary><Drafts drafts={docs.drafts} /></details>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs font-semibold text-slate-700">
                업로드된 파일
              </div>
              <UploadsTable noticeNo={notice.notice_no} uploads={uploads} />
            </div>
            {view === "all" && <ExportButtonGroup noticeNo={notice.notice_no} exports={exports} />}
          </div>
          <UploadDocumentDialog
            key={`upload-${selectedItem || "all"}-${uploadOpen}`}
            defaultItemId={selectedItem}
            open={uploadOpen}
            onClose={() => setUploadOpen(false)}
            notice={notice}
            checklist={docs.checklist}
          />
          <CommonDocumentsDialog
            key={`common-${selectedItem || "all"}-${commonOpen}`}
            defaultItemId={selectedItem}
            open={commonOpen}
            onClose={() => setCommonOpen(false)}
            noticeNo={notice.notice_no}
            checklist={docs.checklist}
          />
        </>
      ) : (
        <div className="rounded border border-slate-200 bg-slate-50/40 p-4 text-sm text-slate-600">
          공고 분석이 완료된 건에서 서류 분석을 실행할 수 있습니다.
        </div>
      )}
    </section>
  );
}

const REVIEW_LABEL: Record<string, string> = {
  pending: "검토 대기",
  approved: "승인",
  rejected: "반려",
};

export function HwpJobs({ noticeNo, jobs, exports = [] }: { noticeNo: string; jobs: HwpJobRecord[]; exports?: ExportRecord[] }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const toast = useToast();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");
  if (jobs.length === 0) return null;

  const review = (job: HwpJobRecord, reviewStatus: "approved" | "rejected") => {
    startTransition(async () => {
      try {
        await actionReviewHwpJob(noticeNo, job.id, { review_status: reviewStatus, review_note: notes[job.id] ?? job.review_note ?? undefined });
        setMessage(`HWP 검토 상태: ${REVIEW_LABEL[reviewStatus]}`);
        toast.push("success", `HWP 검토 상태: ${REVIEW_LABEL[reviewStatus]}`);
        router.refresh();
      } catch (e) {
        setMessage(`검토 상태 저장 실패: ${(e as Error).message}`);
        toast.push("error", `검토 상태 저장 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <div className="min-w-0">
      <div className="mb-2 text-xs font-semibold text-slate-700">HWP 생성/검토</div>
      {message && <div role="status" className="my-2 text-sm">{message}</div>}
      <div className="space-y-2">
        {jobs.map((job) => {
          const requiredMissing = job.missing || [];
          const remaining = job.remaining_placeholders || [];
          const file = exports.find(item => item.id === job.export_id);
          const warning = requiredMissing.length > 0 || remaining.length > 0 || file?.validation_status === "warning" || Boolean(file?.validation_errors?.length);
          return (
            <div key={job.id} className="rounded border border-slate-200 bg-white p-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-slate-800">
                  Job #{job.id} · {job.status === "completed" ? "생성 성공" : job.status === "failed" ? "생성 실패" : "처리 대기/진행 중"} · {REVIEW_LABEL[job.review_status] || job.review_status}
                  {job.created_at && <span className="ml-2">{new Date(job.created_at).toLocaleString("ko-KR")}</span>}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={pending || job.status !== "completed" || !file || file.validation_status === "failed" || (warning && !(notes[job.id] ?? job.review_note)?.trim())}
                    title={job.status !== "completed" ? "생성 완료 후 승인할 수 있습니다" : warning ? "경고 확인 의견이 필요합니다" : "생성물 승인"}
                    onClick={() => review(job, "approved")}
                    className="rounded border border-emerald-700 px-2 py-1 text-emerald-800 disabled:opacity-50"
                  >
                    승인
                  </button>
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => review(job, "rejected")}
                    className="rounded border border-red-800 px-2 py-1 text-red-800 disabled:opacity-50"
                  >
                    반려
                  </button>
                </div>
              </div>
              {file && <a className="work-button mt-2" href={`/api/notices/${encodeURIComponent(noticeNo)}/documents/exports/by-id/${file.id}/download`} download>{warning ? "경고 있음 · " : ""}파일 다운로드</a>}
              {file && <details className="mt-2"><summary>파일 정보</summary><p className="break-all">{file.output_path}</p></details>}
              {job.status === "failed" && <p className="mt-2 text-red-800">생성 실패로 승인할 수 없습니다. 입력값과 Worker 연결을 확인한 뒤 다시 생성하세요.</p>}
              <label className="mt-2 block">검토 의견{warning ? " (승인 시 필수)" : ""}<input aria-label={`Job ${job.id} 검토 의견`} className="work-control mt-1 block w-full" value={notes[job.id] ?? job.review_note ?? ""} onChange={e => setNotes({...notes,[job.id]:e.target.value})}/></label>
              {requiredMissing.length > 0 ? (
                <div className="mt-2 text-amber-900">
                  필수 누락 {requiredMissing.length}개: {requiredMissing.join(", ")}
                </div>
              ) : null}
              {remaining.length > 0 ? (
                <div className="mt-2 text-amber-900">
                  남은 placeholder {remaining.length}개: {remaining.join(", ")}
                </div>
              ) : null}
              {job.error_detail ? (
                <details className="mt-2 text-red-800"><summary>기술 상세</summary><p className="break-all">{job.error_detail}</p></details>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DocumentErrors({ errors }: { errors: Array<Record<string, unknown>> }) {
  const visibleErrors = errors
    .map((error) => ({
      stage: String(error.stage || error.source || "document"),
      detail: String(error.detail || error.message || error.error || "알 수 없는 오류"),
      severity: String(error.severity || "error"),
      fileName: error.file_name ? String(error.file_name) : null,
    }))
    .filter((error) => error.detail.trim().length > 0);
  if (visibleErrors.length === 0) return null;
  return (
    <details className="border-t border-slate-200 py-3 text-sm text-slate-600">
      <summary className="cursor-pointer">이전 실행 이력 · {visibleErrors.length}건</summary>
      <div className="mb-2 text-xs font-semibold text-red-800">
        서류 처리 오류 {visibleErrors.length}건
      </div>
      <ul className="space-y-1">
        {visibleErrors.slice(0, 5).map((error, index) => (
          <li key={`${error.stage}-${index}`} className="text-xs leading-5">
            <span className="font-semibold">{error.stage}</span>
            {error.fileName ? ` · ${error.fileName}` : ""}: {error.detail}
            {error.severity !== "error" ? ` (${error.severity})` : ""}
          </li>
        ))}
      </ul>
      {visibleErrors.length > 5 ? (
        <div className="mt-2 text-xs text-red-800">
          외 {visibleErrors.length - 5}건은 오류 로그를 확인하세요.
        </div>
      ) : null}
    </details>
  );
}

function RemainingPlaceholders({ drafts }: { drafts: Record<string, unknown> }) {
  const draft =
    drafts.bid_form && typeof drafts.bid_form === "object" && !Array.isArray(drafts.bid_form)
      ? (drafts.bid_form as Record<string, unknown>)
      : null;
  const remaining = Array.isArray(draft?.remaining_placeholders)
    ? draft.remaining_placeholders.map(String).filter(Boolean)
    : [];
  if (remaining.length === 0) return null;
  return (
    <div className="rounded border border-amber-800 bg-amber-50/20 p-3 text-sm text-amber-900">
      남은 HWP 입력값 {remaining.length}개: {remaining.join(", ")}
    </div>
  );
}

function ChecklistTable({
  items,
  pending,
  onStatusChange,
  onUpload,
  onCommon,
}: {
  items: DocumentChecklistItem[];
  pending: boolean;
  onStatusChange: (item: DocumentChecklistItem, status: DocumentItemStatus) => void;
  onUpload: (item: DocumentChecklistItem) => void;
  onCommon: (item: DocumentChecklistItem) => void;
}) {
  return (
    <div className="overflow-x-auto rounded border border-slate-200">
      <table className="min-w-[780px] w-full text-sm">
        <thead className="bg-slate-50/80 text-slate-700">
          <tr>
            <th className="px-3 py-2 text-left font-medium">서류</th>
            <th className="px-3 py-2 text-left font-medium">구분</th>
            <th className="px-3 py-2 text-left font-medium">필수</th>
            <th className="px-3 py-2 text-left font-medium">상태</th>
            <th className="px-3 py-2 text-left font-medium">담당</th>
            <th className="px-3 py-2 text-left font-medium">근거</th>
            <th className="px-3 py-2 text-left font-medium">서류 연결</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-t border-slate-200">
              <td className="px-3 py-2 text-slate-900">{item.name}</td>
              <td className="px-3 py-2 text-slate-700">{item.type}</td>
              <td className="px-3 py-2 text-slate-700">
                {item.required ? "필수" : "선택"}
              </td>
              <td className="px-3 py-2">
                <select
                  value={item.status}
                  aria-label={`${item.name} 상태`}
                  disabled={pending}
                  onChange={(e) =>
                    onStatusChange(item, e.target.value as DocumentItemStatus)
                  }
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {STATUS_LABEL[status]}
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-3 py-2 text-slate-700">{item.owner || "-"}</td>
              <td className="px-3 py-2 text-xs text-slate-600">
                {item.reason || item.source}
              </td>
              <td className="px-3 py-2"><div className="flex gap-1"><button className="work-button" aria-label={`${item.name} 업로드`} title="파일 업로드" onClick={() => onUpload(item)}><Upload size={16}/></button><button className="work-button" aria-label={`${item.name} 공통 서류`} title="공통 서류 연결" onClick={() => onCommon(item)}><FolderOpen size={16}/></button></div></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Risks({ risks }: { risks: string[] }) {
  if (risks.length === 0) return null;
  return (
    <div className="rounded border border-amber-800 bg-amber-50/20 p-3">
      <div className="mb-1 text-xs font-semibold text-amber-800">위험/확인 메모</div>
      <ul className="list-disc space-y-1 pl-5 text-sm text-amber-900">
        {risks.map((risk, index) => (
          <li key={`${risk}-${index}`}>{risk}</li>
        ))}
      </ul>
    </div>
  );
}

function Drafts({ drafts }: { drafts: Record<string, unknown> }) {
  const entries = Object.entries(drafts || {});
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {entries.map(([key, value]) => (
        key === "proposal" ? (
          <ProposalDraftView key={key} id={key} value={value} />
        ) : (
          <DraftView key={key} id={key} value={value} />
        )
      ))}
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function DraftView({ id, value }: { id: string; value: unknown }) {
  const draft = asRecord(value);
  const label = String(draft.label || id);
  const content =
    typeof draft.content === "string"
      ? draft.content
      : JSON.stringify(draft.values || draft, null, 2);

  const copy = async () => {
    await navigator.clipboard?.writeText(content);
  };

  return (
    <div className="rounded border border-slate-200 bg-slate-50/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-700">{label}</div>
        <button
          type="button"
          onClick={copy}
          className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
        >
          복사
        </button>
      </div>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-white p-2 text-xs text-slate-800">
        {content}
      </pre>
    </div>
  );
}

function ProposalDraftView({ id, value }: { id: string; value: unknown }) {
  const draft = asRecord(value);
  const label = String(draft.label || id);
  const sections = Array.isArray(draft.sections) ? draft.sections : [];
  const tables = Array.isArray(draft.tables) ? draft.tables : [];
  const required = stringArray(draft.required_placeholders);
  const result = asRecord(draft.result);
  const remaining = stringArray(
    draft.remaining_placeholders ?? result.remaining_placeholders,
  );
  const rawContent = JSON.stringify(draft, null, 2);

  const copy = async () => {
    await navigator.clipboard?.writeText(rawContent);
  };

  return (
    <div className="rounded border border-slate-200 bg-slate-50/40 p-3 lg:col-span-2">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold text-slate-700">{label}</div>
          <div className="mt-1 text-xs text-slate-500">
            섹션 {sections.length}개 · 표 {tables.length}개
            {required.length > 0 ? ` · 필수값 ${required.length}개` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={copy}
          className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
        >
          원본 복사
        </button>
      </div>

      {remaining.length > 0 ? (
        <div className="mb-3 rounded border border-amber-800 bg-amber-50/20 p-2 text-xs text-amber-900">
          남은 placeholder {remaining.length}개: {remaining.join(", ")}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-600">제안서 섹션</div>
          {sections.length > 0 ? (
            sections.map((section, index) => {
              const record = asRecord(section);
              const title = String(record.title || `섹션 ${index + 1}`);
              const content = String(record.content || "").trim();
              return (
                <div key={`${title}-${index}`} className="rounded bg-white p-2">
                  <div className="text-xs font-semibold text-slate-800">{title}</div>
                  {content ? (
                    <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-600">
                      {content}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-slate-600">본문 없음</p>
                  )}
                </div>
              );
            })
          ) : (
            <div className="rounded bg-white p-2 text-xs text-slate-500">
              생성된 섹션이 없습니다.
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-600">포함 표</div>
          {tables.length > 0 ? (
            tables.map((table, index) => {
              const record = asRecord(table);
              const title = String(record.title || `표 ${index + 1}`);
              const rows = Array.isArray(record.rows) ? record.rows : [];
              return (
                <div key={`${title}-${index}`} className="rounded bg-white p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold text-slate-800">{title}</div>
                    <div className="text-xs text-slate-500">행 {rows.length}개</div>
                  </div>
                  {rows.length > 0 ? (
                    <div className="mt-2 max-h-40 overflow-auto">
                      <table className="w-full text-xs">
                        <tbody>
                          {rows.slice(0, 5).map((row, rowIndex) => {
                            const cells = Array.isArray(row)
                              ? row.map(String)
                              : Object.values(asRecord(row)).map(String);
                            return (
                              <tr key={rowIndex} className="border-t border-slate-200">
                                {cells.slice(0, 4).map((cell, cellIndex) => (
                                  <td
                                    key={`${rowIndex}-${cellIndex}`}
                                    className="px-2 py-1 text-slate-600"
                                  >
                                    {cell || "-"}
                                  </td>
                                ))}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="mt-1 text-xs text-slate-600">표 행 없음</p>
                  )}
                </div>
              );
            })
          ) : (
            <div className="rounded bg-white p-2 text-xs text-slate-500">
              생성된 표가 없습니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
