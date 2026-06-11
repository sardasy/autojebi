"use client";

import { useTransition } from "react";

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
};

export function ExportButtonGroup({ noticeNo, exports }: Props) {
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const byKind = new Map<ExportKind, ExportRecord>();
  for (const rec of exports) {
    if (rec.kind === "excel" || rec.kind === "hwp") {
      byKind.set(rec.kind, rec);
    }
  }

  const generate = (kind: ExportKind) => {
    startTransition(async () => {
      try {
        const r = await actionExportDocument(noticeNo, kind);
        toast.push(
          "success",
          `${KIND_LABELS[kind]} 파일 생성 완료: ${r.export.output_path}`,
        );
      } catch (e) {
        toast.push("error", `${KIND_LABELS[kind]} 생성 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
      <div className="mb-2 text-xs font-semibold text-slate-300">
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
                className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
              >
                {pending ? "생성 중…" : `${KIND_LABELS[kind]} 생성`}
              </button>
              {existing ? (
                <a
                  href={`/api/notices/${encodeURIComponent(noticeNo)}/documents/exports/${kind}/download`}
                  className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
                  download={`${noticeNo}-compliance.${kind === "excel" ? "xlsx" : "hwp"}`}
                >
                  ⬇ 다운로드
                </a>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        HWP 출력은 Windows 데스크톱의 milim-hwp-agent가 가동돼 있어야 합니다 (
        <code>POST /document/insert-table</code> 위임). 에이전트 미가동 시 502가 반환되며,
        Excel은 에이전트 없이도 항상 정상 동작합니다.
      </p>
    </div>
  );
}
