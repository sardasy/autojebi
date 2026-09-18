"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

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
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();

  const submit = () => {
    setResultMessage(dryRun ? "알림 dry-run 실행 중입니다." : "Teams 알림 전송 중입니다.");
    startTransition(async () => {
      try {
        const r = await actionNotify(noticeNo, dryRun);
        const message = `알림 완료 — 상태: ${r.status}, 전송: ${
          r.delivered ? "예" : "아니오 (dry_run)"
        }`;
        setResultMessage(message);
        toast.push("success", message);
        router.refresh();
      } catch (e) {
        const message = `알림 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="Teams 알림" size="sm">
      <div className="space-y-4">
        <p className="text-sm text-slate-700">
            Teams 알림을 실행합니다. 공고 상태와 참가 결정은 변경하지 않습니다.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            className="accent-brand-500"
          />
          <span>
              Dry run (Webhook <strong>발송 안함</strong>, 기록만 저장)
          </span>
        </label>
        {resultMessage ? (
          <div role="status" className="rounded border border-slate-300 bg-slate-50/70 p-3 text-sm text-slate-900">
            {resultMessage}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
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
