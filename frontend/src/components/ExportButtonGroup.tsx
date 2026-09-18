"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { actionExportDocument } from "@/lib/actions";
import type { ExportKind, ExportRecord } from "@/lib/api";
import { useToast } from "./Toast";

type Props = {
  noticeNo: string;
  exports: ExportRecord[];
};

const KIND_LABELS: Record<ExportKind, string> = {
  excel: "Excel",
  hwp: "HWP",
  bid_form_hwp: "입찰양식 HWP",
  proposal_hwp: "제안서 HWP",
};

const VALIDATION_LABELS: Record<string, string> = {
  passed: "검증 통과",
  warning: "검토 필요",
  failed: "검증 실패",
};

// 다운로드는 항상 허용하되, 검증 결과가 warning/failed면 시각적으로 강조한다.
const DOWNLOAD_LINK_CLASS: Record<string, string> = {
  warning: "border-amber-500/70 bg-amber-500/10 text-amber-800 hover:bg-amber-500/20",
  failed: "border-rose-500/70 bg-rose-500/10 text-rose-800 hover:bg-rose-500/20",
  default: "border-slate-300 text-slate-800 hover:bg-slate-100",
};

const VALIDATION_BADGE_CLASS: Record<string, string> = {
  warning: "border-amber-500/60 bg-amber-500/15 text-amber-800",
  failed: "border-rose-500/60 bg-rose-500/15 text-rose-800",
  passed: "border-emerald-500/50 bg-emerald-500/10 text-emerald-800",
};

function downloadHref(noticeNo: string, rec: ExportRecord): string {
  if (rec.id) {
    return `/api/notices/${encodeURIComponent(noticeNo)}/documents/exports/by-id/${rec.id}/download`;
  }
  return `/api/notices/${encodeURIComponent(noticeNo)}/documents/exports/${rec.kind}/download`;
}

function exportSummary(rec: ExportRecord): string {
  const parts = [
    rec.version || rec.template_version,
    rec.file_size ? `${Math.ceil(rec.file_size / 1024)}KB` : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

function ValidationBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const cls = VALIDATION_BADGE_CLASS[status] || VALIDATION_BADGE_CLASS.passed;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {VALIDATION_LABELS[status] || status}
    </span>
  );
}

function DownloadLink({
  noticeNo,
  rec,
  downloadName,
  label,
}: {
  noticeNo: string;
  rec: ExportRecord;
  downloadName: string;
  label: string;
}) {
  const status = rec.validation_status;
  const linkCls =
    status === "warning" || status === "failed"
      ? DOWNLOAD_LINK_CLASS[status]
      : DOWNLOAD_LINK_CLASS.default;
  const summary = exportSummary(rec);
  return (
    <div className="flex items-center gap-2">
      <a
        href={downloadHref(noticeNo, rec)}
        className={`rounded border px-3 py-1.5 text-sm ${linkCls}`}
        download={downloadName}
        title={
          status === "warning"
            ? "검토 경고가 있는 파일입니다"
            : status === "failed"
              ? "검증에 실패한 파일입니다"
              : undefined
        }
      >
        {label}
      </a>
      <ValidationBadge status={status} />
      {summary ? <span className="text-xs text-slate-600">{summary}</span> : null}
    </div>
  );
}

export function ExportButtonGroup({ noticeNo, exports }: Props) {
  const [pending, startTransition] = useTransition();
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const toast = useToast();
  const router = useRouter();

  const byKind = new Map<ExportKind, ExportRecord>();
  for (const rec of exports) {
    if (
      rec.kind === "excel" ||
      rec.kind === "hwp" ||
      rec.kind === "bid_form_hwp" ||
      rec.kind === "proposal_hwp"
    ) {
      byKind.set(rec.kind, rec);
    }
  }

  const generate = (kind: ExportKind) => {
    setResultMessage(`${KIND_LABELS[kind]} 파일 생성 중입니다.`);
    startTransition(async () => {
      try {
        const r = await actionExportDocument(noticeNo, kind);
        const message = `${KIND_LABELS[kind]} 파일 생성 완료: ${r.export.output_path}`;
        setResultMessage(message);
        toast.push("success", message);
        router.refresh();
      } catch (e) {
        const message = `${KIND_LABELS[kind]} 생성 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  return (
    <div className="min-w-0">
      <div className="mb-2 text-xs font-semibold text-slate-700">
        규격대응표 내보내기
      </div>
      <div className="flex flex-wrap gap-2">
        {(["excel", "hwp"] as ExportKind[]).map((kind) => {
          const existing = byKind.get(kind);
          return (
            <div key={kind} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => generate(kind)}
                disabled={pending}
                className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-600"
              >
                {pending ? "생성 중…" : `${KIND_LABELS[kind]} 생성`}
              </button>
              {existing ? (
                <DownloadLink
                  noticeNo={noticeNo}
                  rec={existing}
                  downloadName={`${noticeNo}-compliance.${kind === "excel" ? "xlsx" : "hwp"}`}
                  label="다운로드"
                />
              ) : null}
            </div>
          );
        })}
        {byKind.get("proposal_hwp") ? (
          <DownloadLink
            noticeNo={noticeNo}
            rec={byKind.get("proposal_hwp") as ExportRecord}
            downloadName={`${noticeNo}-proposal.hwp`}
            label="제안서 HWP 다운로드"
          />
        ) : null}
        {byKind.get("bid_form_hwp") ? (
          <DownloadLink
            noticeNo={noticeNo}
            rec={byKind.get("bid_form_hwp") as ExportRecord}
            downloadName={`${noticeNo}-bid-form.hwp`}
            label="입찰양식 HWP 다운로드"
          />
        ) : null}
      </div>
      {resultMessage ? (
        <div role="status" className="mt-3 rounded border border-slate-300 bg-white p-2 text-xs text-slate-800">
          {resultMessage}
        </div>
      ) : null}
    </div>
  );
}
