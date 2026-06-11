"use client";

import { useState, useTransition } from "react";

import { actionAnalyze } from "@/lib/actions";
import type { NoticeRecord } from "@/lib/api";
import { GradeDialog } from "./GradeDialog";
import { useToast } from "./Toast";

type Props = { notice: NoticeRecord };

type DialogKind = "grade" | null;

export function NoticeActionsBar({ notice }: Props) {
  const [openDialog, setOpenDialog] = useState<DialogKind>(null);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const analyzeDisabled = notice.status !== "collected" || pending;
  const gradeDisabled = notice.status === "collected" || pending;

  const onAnalyze = () => {
    startTransition(async () => {
      try {
        const r = await actionAnalyze(notice.notice_no);
        toast.push(
          "success",
          `분석 완료 — 카테고리: ${r.category}, fit_score: ${r.fit_score}, 담당자: ${r.assignee}`,
        );
      } catch (e) {
        toast.push("error", `분석 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="분석"
          onClick={onAnalyze}
          disabled={analyzeDisabled}
          hint={notice.status !== "collected" ? "이미 분석됨" : undefined}
        />
        <ActionButton
          label="그레이드"
          onClick={() => setOpenDialog("grade")}
          disabled={gradeDisabled}
          hint={notice.status === "collected" ? "분석 후 가능" : undefined}
        />
      </div>
      <GradeDialog
        open={openDialog === "grade"}
        onClose={() => setOpenDialog(null)}
        noticeNo={notice.notice_no}
      />
    </>
  );
}

function ActionButton({
  label,
  onClick,
  disabled,
  hint,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  hint?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={hint}
      className="rounded bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:bg-slate-700 disabled:text-slate-400 disabled:cursor-not-allowed"
    >
      {label}
    </button>
  );
}
