"use client";

import { useMemo, useState, useTransition } from "react";

import {
  actionAnalyzeDocuments,
  actionUpdateDocumentChecklistItem,
  actionValidateDocuments,
} from "@/lib/actions";
import type {
  DocumentChecklistItem,
  DocumentItemStatus,
  NoticeRecord,
} from "@/lib/api";
import {
  documentSummaryText,
  readDocumentAutomation,
} from "@/lib/documentAutomation";
import { ExportButtonGroup } from "./ExportButtonGroup";
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
  const toast = useToast();
  const docs = useMemo(() => readDocumentAutomation(notice), [notice]);
  const canAnalyze = notice.status === "analyzed" || notice.status === "form_filled";
  const uploads = docs?.uploads || [];
  const exports = docs?.exports || [];

  const analyze = () => {
    startTransition(async () => {
      try {
        const r = await actionAnalyzeDocuments(notice.notice_no);
        toast.push(
          "success",
          `서류 분석 완료: ${r.document_automation.checklist.length}개 항목`,
        );
      } catch (e) {
        toast.push("error", `서류 분석 실패: ${(e as Error).message}`);
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
        <div className="flex gap-2">
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
        </>
      ) : (
        <div className="rounded border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
          공고 분석이 완료된 건에서 서류 분석을 실행할 수 있습니다.
        </div>
      )}
    </section>
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
        <DraftView key={key} id={key} value={value} />
      ))}
    </div>
  );
}

function DraftView({ id, value }: { id: string; value: unknown }) {
  const draft = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
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
