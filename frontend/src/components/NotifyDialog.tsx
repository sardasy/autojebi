"use client";

import { useState, useTransition } from "react";

import { actionNotify } from "@/lib/actions";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  noticeNo: string;
};

export function NotifyDialog({ open, onClose, noticeNo }: Props) {
  const [dryRun, setDryRun] = useState(true);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const submit = () => {
    startTransition(async () => {
      try {
        const r = await actionNotify(noticeNo, dryRun);
        toast.push(
          "success",
          `알림 완료 — 상태: ${r.status}, 전송: ${r.delivered ? "예" : "아니오 (dry_run)"}`,
        );
        onClose();
      } catch (e) {
        toast.push("error", `알림 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="Teams 알림" size="sm">
      <div className="space-y-4">
        <p className="text-sm text-slate-300">
          fit_score에 따라 상태 전환 + Teams Webhook 발송. dry_run이면 전송하지 않습니다.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            className="accent-brand-500"
          />
          <span>
            Dry run (Webhook <strong>발송 안함</strong>, 상태 전환만)
          </span>
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
