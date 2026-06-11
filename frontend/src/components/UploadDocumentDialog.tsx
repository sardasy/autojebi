"use client";

import { useMemo, useRef, useState, useTransition } from "react";

import { actionUploadDocument } from "@/lib/actions";
import type { DocumentChecklistItem, NoticeRecord } from "@/lib/api";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  notice: NoticeRecord;
  /** 패널이 가지고 있는 체크리스트 — 매핑 select 옵션. */
  checklist: DocumentChecklistItem[];
  /** 모달 열 때 기본으로 선택된 항목 (예: 표에서 "업로드" 버튼 클릭 시). */
  defaultItemId?: string;
};

export function UploadDocumentDialog({
  open,
  onClose,
  notice,
  checklist,
  defaultItemId,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [itemId, setItemId] = useState<string>(defaultItemId || "");
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const reset = () => {
    setFile(null);
    setItemId(defaultItemId || "");
    if (inputRef.current) inputRef.current.value = "";
  };

  const close = () => {
    if (pending) return;
    reset();
    onClose();
  };

  const itemOptions = useMemo(
    () => checklist.filter((item) => item.required || item.status !== "not_applicable"),
    [checklist],
  );

  const submit = () => {
    if (!file) {
      toast.push("error", "파일을 선택해주세요.");
      return;
    }
    startTransition(async () => {
      try {
        const r = await actionUploadDocument(
          notice.notice_no,
          file,
          itemId || undefined,
        );
        toast.push(
          "success",
          `${r.uploaded.name} 업로드 완료 (${formatBytes(r.uploaded.size)})`,
        );
        reset();
        onClose();
      } catch (e) {
        toast.push("error", `업로드 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <Modal open={open} onClose={close} title="서류 파일 업로드" size="md">
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-300">
            파일 선택
          </label>
          <input
            ref={inputRef}
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 file:mr-3 file:rounded file:border-0 file:bg-brand-500 file:px-3 file:py-1 file:text-xs file:text-white"
            accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,.xlsx,.docx"
          />
          {file ? (
            <p className="mt-1 text-xs text-slate-400">
              선택됨: {file.name} ({formatBytes(file.size)})
            </p>
          ) : null}
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-300">
            연결할 체크리스트 항목 (선택)
          </label>
          <select
            value={itemId}
            onChange={(e) => setItemId(e.target.value)}
            className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="">(매핑 없음)</option>
            {itemOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.id})
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">
            매핑하면 해당 항목 상태가 자동으로 ready로 승격됩니다.
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={close}
            disabled={pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!file || pending}
            className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {pending ? "업로드 중…" : "업로드"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
