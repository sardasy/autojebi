"use client";

import { useState, useTransition } from "react";

import { actionGrade } from "@/lib/actions";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  noticeNo: string;
};

export function GradeDialog({ open, onClose, noticeNo }: Props) {
  const [alert, setAlert] = useState(true);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const submit = () => {
    startTransition(async () => {
      try {
        const r = await actionGrade(noticeNo, alert);
        toast.push(
          "success",
          `그레이드 완료: 종합 ${r.score_total.toFixed(2)} ` +
            `(사양 ${r.score_spec.toFixed(2)} · 자격 ${r.score_qual.toFixed(2)} · 예가 ${r.score_price.toFixed(2)})\n` +
            `Slack: ${r.slack_delivered ? "발송됨" : "미발송"}`,
        );
        onClose();
      } catch (e) {
        toast.push("error", `그레이드 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="그레이드 실행" size="sm">
      <div className="space-y-4">
        <p className="text-sm text-slate-300">
          ElecSpec → Qdrant SKU 매칭 → 3축 점수 산출. fit_score가 자동 동기화됩니다.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={alert}
            onChange={(e) => setAlert(e.target.checked)}
            className="accent-brand-500"
          />
          <span>Slack 알림 (임계치 초과 시)</span>
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={pending}
            className="rounded bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "실행 중…" : "실행"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
