"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import {
  actionComposeHwpDocuments,
  actionComposeProposalDocument,
  actionGetHwpAgentHealth,
} from "@/lib/actions";
import type { ExportKind, ExportRecord } from "@/lib/api";
import { useToast } from "./Toast";

const KIND_LABELS: Record<ExportKind, string> = {
  excel: "규격대응표 Excel",
  hwp: "규격대응표 HWP",
  bid_form_hwp: "입찰참가신청서 HWP",
  proposal_hwp: "제안서 HWP",
};

const EXT: Record<ExportKind, string> = {
  excel: "xlsx",
  hwp: "hwp",
  bid_form_hwp: "hwp",
  proposal_hwp: "hwp",
};

function downloadHref(noticeNo: string, rec: ExportRecord): string {
  if (rec.id) {
    return `/api/notices/${encodeURIComponent(noticeNo)}/documents/exports/by-id/${rec.id}/download`;
  }
  return `/api/notices/${encodeURIComponent(noticeNo)}/documents/exports/${rec.kind}/download`;
}

type ComposeError = { stage?: string; detail?: string };

export function ComposeStep({
  noticeNo,
  exports,
}: {
  noticeNo: string;
  exports: ExportRecord[];
}) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [agent, setAgent] = useState<"checking" | "ok" | "unavailable">("checking");
  const [missingDocErrors, setMissingDocErrors] = useState<ComposeError[]>([]);

  useEffect(() => {
    actionGetHwpAgentHealth()
      .then((r) => setAgent(r.ok ? "ok" : "unavailable"))
      .catch(() => setAgent("unavailable"));
  }, []);

  const generate = () => {
    setMissingDocErrors([]);
    start(async () => {
      try {
        const bid = await actionComposeHwpDocuments(noticeNo, {
          include_bid_form: true,
          include_technical_compliance: true,
        });
        const proposal = await actionComposeProposalDocument(noticeNo, {});
        const allErrors: ComposeError[] = [...(bid.errors || []), ...(proposal.errors || [])];
        // 실제 "필수 서류 누락" 차단 사유만 배너로 노출한다. pre_compose.spec_review(규격 검토 권장),
        // hwp.remaining_placeholders 등은 경고일 뿐 차단이 아니므로 누락 배너에서 제외.
        const missing = allErrors.filter((e) =>
          (e.stage || "").startsWith("pre_compose.required"),
        );
        const produced =
          Boolean(bid.bid_form || bid.technical_compliance || bid.job) ||
          Boolean(proposal.export || proposal.job);

        router.refresh();

        if (missing.length > 0) {
          setMissingDocErrors(missing);
          toast.push("error", `필수 서류 누락 ${missing.length}건 — 2단계에서 보완하세요`);
        } else if (produced) {
          toast.push("success", "서류 생성 완료");
        } else if (allErrors.length > 0) {
          toast.push(
            "error",
            `서류 생성 실패: ${allErrors.map((e) => e.detail).filter(Boolean).join("; ") || "오류"}`,
          );
        } else {
          toast.push("info", "생성된 항목이 없습니다");
        }
      } catch (e) {
        toast.push("error", `서류 생성 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <div className="space-y-4">
      <div
        className={`rounded border px-3 py-2 text-xs ${
          agent === "ok"
            ? "border-emerald-800 bg-emerald-950/20 text-emerald-100"
            : agent === "checking"
              ? "border-slate-700 bg-slate-900/50 text-slate-300"
              : "border-amber-800 bg-amber-950/20 text-amber-100"
        }`}
      >
        HWP 에이전트:{" "}
        {agent === "ok" ? "연결됨" : agent === "checking" ? "확인 중…" : "미연결 (Windows 데스크톱 실행 필요)"}
      </div>

      <button
        type="button"
        onClick={generate}
        disabled={pending}
        className="rounded bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {pending ? "생성 중…" : "서류 생성"}
      </button>

      {missingDocErrors.length > 0 ? (
        <div className="rounded border border-amber-700 bg-amber-950/30 p-3 text-sm text-amber-100">
          <p className="font-medium">필수 서류가 누락되어 일부 문서를 만들 수 없습니다.</p>
          <ul className="mt-1 list-disc pl-5 text-xs text-amber-200">
            {missingDocErrors.map((e, i) => (
              <li key={i}>{e.detail}</li>
            ))}
          </ul>
          <Link
            href={`/notices/${encodeURIComponent(noticeNo)}/analyze`}
            className="mt-2 inline-block rounded border border-amber-600 px-3 py-1 text-xs hover:bg-amber-900/40"
          >
            ← 2단계(필요서류분석)로 이동
          </Link>
        </div>
      ) : null}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-300">생성된 서류</h2>
        {exports.length === 0 ? (
          <p className="text-sm text-slate-500">아직 생성된 서류가 없습니다. "서류 생성"을 눌러주세요.</p>
        ) : (
          <ul className="space-y-2">
            {exports.map((rec) => {
              const warn = rec.validation_status === "warning" || rec.validation_status === "failed";
              return (
                <li
                  key={`${rec.kind}-${rec.id ?? rec.output_path}`}
                  className="flex items-center gap-3 rounded border border-slate-800 bg-slate-900/40 p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-slate-100">
                      {KIND_LABELS[rec.kind] || rec.kind}
                    </div>
                    <div className="truncate text-xs text-slate-500">{rec.output_path}</div>
                  </div>
                  {warn ? (
                    <span className="shrink-0 rounded border border-amber-600/60 bg-amber-500/15 px-1.5 py-0.5 text-[11px] text-amber-200">
                      검토 필요
                    </span>
                  ) : null}
                  <a
                    href={downloadHref(noticeNo, rec)}
                    download={`${noticeNo}-${rec.kind}.${EXT[rec.kind] || "bin"}`}
                    className={`shrink-0 rounded border px-3 py-1.5 text-xs ${
                      warn
                        ? "border-amber-500/70 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20"
                        : "border-slate-700 text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    다운로드
                  </a>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
