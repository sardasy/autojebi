"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

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

export function DocumentPreparationPanel({ notice }: Props) {
  const [pending, startTransition] = useTransition();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [commonOpen, setCommonOpen] = useState(false);
  const toast = useToast();
  const router = useRouter();
  const docs = useMemo(() => readDocumentAutomation(notice), [notice]);
  const canAnalyze = notice.status !== "collected";
  const uploads = docs?.uploads || [];
  const exports = docs?.exports || [];
  const hwpJobs = docs?.hwp_jobs || [];

  const analyze = () => {
    startTransition(async () => {
      try {
        const r = await actionAnalyzeDocuments(notice.notice_no);
        toast.push(
          "success",
          `서류 분석 완료: ${r.document_automation.checklist.length}개 항목`,
        );
        router.refresh();
      } catch (e) {
        toast.push("error", `서류 분석 실패: ${(e as Error).message}`);
      }
    });
  };

  const fetchAttachments = () => {
    startTransition(async () => {
      try {
        const r = await actionFetchG2BAttachments(notice.notice_no);
        const suffix =
          r.errors.length > 0 ? ` · 오류 ${r.errors.length}건 기록` : "";
        toast.push(
          r.fetched.length > 0 ? "success" : "info",
          `첨부 서류 가져오기 완료: ${r.fetched.length}개${suffix}`,
        );
        router.refresh();
      } catch (e) {
        toast.push("error", `첨부 서류 가져오기 실패: ${(e as Error).message}`);
      }
    });
  };

  const validate = () => {
    startTransition(async () => {
      try {
        const r = await actionValidateDocuments(notice.notice_no);
        if (r.ready_for_submission) {
          toast.push("success", "제출 전 검증 통과: 필수 누락 항목이 없습니다.");
        } else {
          toast.push(
            "info",
            `필수 누락 ${r.missing_required.length}건: ${r.missing_required
              .map((item) => item.name)
              .join(", ")}`,
          );
        }
        router.refresh();
      } catch (e) {
        toast.push("error", `검증 실패: ${(e as Error).message}`);
      }
    });
  };

  const updateStatus = (item: DocumentChecklistItem, status: DocumentItemStatus) => {
    startTransition(async () => {
      try {
        await actionUpdateDocumentChecklistItem(notice.notice_no, item.id, { status });
        toast.push("success", `${item.name}: ${STATUS_LABEL[status]} 저장`);
        router.refresh();
      } catch (e) {
        toast.push("error", `상태 저장 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-300">서류 준비</h2>
          {docs ? (
            <p className="mt-1 text-xs text-slate-500">
              {documentSummaryText(docs)} · source: {docs.source}
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
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            첨부 서류 가져오기
          </button>
          <button
            type="button"
            onClick={analyze}
            disabled={!canAnalyze || pending}
            className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            서류 분석
          </button>
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            disabled={!docs || pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            파일 업로드
          </button>
          <button
            type="button"
            onClick={() => setCommonOpen(true)}
            disabled={!docs || pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            공통 서류 가져오기
          </button>
          <button
            type="button"
            onClick={validate}
            disabled={!docs || pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            제출 전 검증
          </button>
        </div>
      </div>

      {docs ? (
        <>
          <DocumentErrors errors={docs.errors} />
          <RemainingPlaceholders drafts={docs.drafts} />
          <HwpJobs noticeNo={notice.notice_no} jobs={hwpJobs} />
          <SpecItemsPanel notice={notice} enabled={Boolean(docs)} />
          <ChecklistTable
            items={docs.checklist}
            pending={pending}
            onStatusChange={updateStatus}
          />
          <Risks risks={docs.risks} />
          <Drafts drafts={docs.drafts} />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs font-semibold text-slate-300">
                업로드된 파일
              </div>
              <UploadsTable noticeNo={notice.notice_no} uploads={uploads} />
            </div>
            <ExportButtonGroup noticeNo={notice.notice_no} exports={exports} />
          </div>
          <UploadDocumentDialog
            open={uploadOpen}
            onClose={() => setUploadOpen(false)}
            notice={notice}
            checklist={docs.checklist}
          />
          <CommonDocumentsDialog
            open={commonOpen}
            onClose={() => setCommonOpen(false)}
            noticeNo={notice.notice_no}
            checklist={docs.checklist}
          />
        </>
      ) : (
        <div className="rounded border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
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

function HwpJobs({ noticeNo, jobs }: { noticeNo: string; jobs: HwpJobRecord[] }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const toast = useToast();
  if (jobs.length === 0) return null;

  const review = (job: HwpJobRecord, reviewStatus: "approved" | "rejected") => {
    startTransition(async () => {
      try {
        await actionReviewHwpJob(noticeNo, job.id, { review_status: reviewStatus });
        toast.push("success", `HWP 검토 상태: ${REVIEW_LABEL[reviewStatus]}`);
        router.refresh();
      } catch (e) {
        toast.push("error", `검토 상태 저장 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
      <div className="mb-2 text-xs font-semibold text-slate-300">HWP 생성/검토</div>
      <div className="space-y-2">
        {jobs.slice(0, 5).map((job) => {
          const requiredMissing = job.missing || [];
          const remaining = job.remaining_placeholders || [];
          return (
            <div key={job.id} className="rounded border border-slate-800 bg-slate-950 p-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-slate-200">
                  Job #{job.id} · {job.status} · {REVIEW_LABEL[job.review_status] || job.review_status}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => review(job, "approved")}
                    className="rounded border border-emerald-700 px-2 py-1 text-emerald-100 disabled:opacity-50"
                  >
                    승인
                  </button>
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => review(job, "rejected")}
                    className="rounded border border-red-800 px-2 py-1 text-red-100 disabled:opacity-50"
                  >
                    반려
                  </button>
                </div>
              </div>
              {requiredMissing.length > 0 ? (
                <div className="mt-2 text-amber-100">
                  필수 누락 {requiredMissing.length}개: {requiredMissing.join(", ")}
                </div>
              ) : null}
              {remaining.length > 0 ? (
                <div className="mt-2 text-amber-100">
                  남은 placeholder {remaining.length}개: {remaining.join(", ")}
                </div>
              ) : null}
              {job.error_detail ? (
                <div className="mt-2 text-red-100">{job.error_detail}</div>
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
    <div className="rounded border border-red-900 bg-red-950/25 p-3 text-sm text-red-100">
      <div className="mb-2 text-xs font-semibold text-red-200">
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
        <div className="mt-2 text-xs text-red-200">
          외 {visibleErrors.length - 5}건은 오류 로그를 확인하세요.
        </div>
      ) : null}
    </div>
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
    <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-sm text-amber-100">
      남은 HWP 입력값 {remaining.length}개: {remaining.join(", ")}
    </div>
  );
}

function ChecklistTable({
  items,
  pending,
  onStatusChange,
}: {
  items: DocumentChecklistItem[];
  pending: boolean;
  onStatusChange: (item: DocumentChecklistItem, status: DocumentItemStatus) => void;
}) {
  return (
    <div className="overflow-x-auto rounded border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900/80 text-slate-300">
          <tr>
            <th className="px-3 py-2 text-left font-medium">서류</th>
            <th className="px-3 py-2 text-left font-medium">구분</th>
            <th className="px-3 py-2 text-left font-medium">필수</th>
            <th className="px-3 py-2 text-left font-medium">상태</th>
            <th className="px-3 py-2 text-left font-medium">담당</th>
            <th className="px-3 py-2 text-left font-medium">근거</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-t border-slate-800">
              <td className="px-3 py-2 text-slate-100">{item.name}</td>
              <td className="px-3 py-2 text-slate-300">{item.type}</td>
              <td className="px-3 py-2 text-slate-300">
                {item.required ? "필수" : "선택"}
              </td>
              <td className="px-3 py-2">
                <select
                  value={item.status}
                  disabled={pending}
                  onChange={(e) =>
                    onStatusChange(item, e.target.value as DocumentItemStatus)
                  }
                  className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs"
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {STATUS_LABEL[status]}
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-3 py-2 text-slate-300">{item.owner || "-"}</td>
              <td className="px-3 py-2 text-xs text-slate-400">
                {item.reason || item.source}
              </td>
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
    <div className="rounded border border-amber-800 bg-amber-950/20 p-3">
      <div className="mb-1 text-xs font-semibold text-amber-200">위험/확인 메모</div>
      <ul className="list-disc space-y-1 pl-5 text-sm text-amber-100">
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
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-300">{label}</div>
        <button
          type="button"
          onClick={copy}
          className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
        >
          복사
        </button>
      </div>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-2 text-xs text-slate-200">
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
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3 lg:col-span-2">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold text-slate-300">{label}</div>
          <div className="mt-1 text-xs text-slate-500">
            섹션 {sections.length}개 · 표 {tables.length}개
            {required.length > 0 ? ` · 필수값 ${required.length}개` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={copy}
          className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
        >
          원본 복사
        </button>
      </div>

      {remaining.length > 0 ? (
        <div className="mb-3 rounded border border-amber-800 bg-amber-950/20 p-2 text-xs text-amber-100">
          남은 placeholder {remaining.length}개: {remaining.join(", ")}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-400">제안서 섹션</div>
          {sections.length > 0 ? (
            sections.map((section, index) => {
              const record = asRecord(section);
              const title = String(record.title || `섹션 ${index + 1}`);
              const content = String(record.content || "").trim();
              return (
                <div key={`${title}-${index}`} className="rounded bg-slate-950 p-2">
                  <div className="text-xs font-semibold text-slate-200">{title}</div>
                  {content ? (
                    <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-400">
                      {content}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-slate-600">본문 없음</p>
                  )}
                </div>
              );
            })
          ) : (
            <div className="rounded bg-slate-950 p-2 text-xs text-slate-500">
              생성된 섹션이 없습니다.
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-400">포함 표</div>
          {tables.length > 0 ? (
            tables.map((table, index) => {
              const record = asRecord(table);
              const title = String(record.title || `표 ${index + 1}`);
              const rows = Array.isArray(record.rows) ? record.rows : [];
              return (
                <div key={`${title}-${index}`} className="rounded bg-slate-950 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold text-slate-200">{title}</div>
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
                              <tr key={rowIndex} className="border-t border-slate-800">
                                {cells.slice(0, 4).map((cell, cellIndex) => (
                                  <td
                                    key={`${rowIndex}-${cellIndex}`}
                                    className="px-2 py-1 text-slate-400"
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
            <div className="rounded bg-slate-950 p-2 text-xs text-slate-500">
              생성된 표가 없습니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
