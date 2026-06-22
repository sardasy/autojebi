"use client";

import { useEffect, useRef, useState, useTransition } from "react";

import {
  actionImportCommonUpload,
  actionListCommonUploads,
  actionUploadCommonDocument,
} from "@/lib/actions";
import type { DocumentChecklistItem, UploadedDocument } from "@/lib/api";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  noticeNo: string;
  checklist: DocumentChecklistItem[];
};

export function CommonDocumentsDialog({
  open,
  onClose,
  noticeNo,
  checklist,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadedDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [itemId, setItemId] = useState("");
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const refresh = () => {
    startTransition(async () => {
      try {
        const r = await actionListCommonUploads();
        setItems(r.items);
      } catch (e) {
        toast.push("error", `공통 서류 목록 실패: ${(e as Error).message}`);
      }
    });
  };

  useEffect(() => {
    if (open) refresh();
  }, [open]);

  const upload = () => {
    if (!file) {
      toast.push("error", "공통 서류로 등록할 파일을 선택해주세요.");
      return;
    }
    startTransition(async () => {
      try {
        const r = await actionUploadCommonDocument(file, itemId || undefined);
        toast.push("success", `${r.uploaded.name} 공통 서류 등록`);
        setFile(null);
        if (inputRef.current) inputRef.current.value = "";
        refresh();
      } catch (e) {
        toast.push("error", `공통 서류 등록 실패: ${(e as Error).message}`);
      }
    });
  };

  const importItem = (uploadId: string, name: string) => {
    startTransition(async () => {
      try {
        await actionImportCommonUpload(noticeNo, uploadId);
        toast.push("success", `${name} 가져오기 완료`);
        onClose();
      } catch (e) {
        toast.push("error", `가져오기 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="공통 서류 가져오기" size="lg">
      <div className="space-y-4">
        <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
          <div className="mb-2 text-xs font-semibold text-slate-300">
            공통 서류 등록
          </div>
          <div className="grid gap-2 md:grid-cols-[1fr_220px_auto]">
            <input
              ref={inputRef}
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 file:mr-3 file:rounded file:border-0 file:bg-brand-500 file:px-3 file:py-1 file:text-xs file:text-white"
              accept=".pdf,.hwp,.hwpx,.jpg,.jpeg,.png,.xlsx,.docx"
            />
            <select
              value={itemId}
              onChange={(e) => setItemId(e.target.value)}
              className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              <option value="">자동 추천</option>
              {checklist.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={upload}
              disabled={pending || !file}
              className="rounded bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              등록
            </button>
          </div>
        </div>

        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/80 text-slate-300">
              <tr>
                <th className="px-3 py-2 text-left font-medium">파일</th>
                <th className="px-3 py-2 text-left font-medium">추천/연결</th>
                <th className="px-3 py-2 text-left font-medium">요약</th>
                <th className="px-3 py-2 text-right font-medium">동작</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-5 text-center text-slate-400">
                    등록된 공통 서류가 없습니다.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id} className="border-t border-slate-800">
                    <td className="px-3 py-2 text-slate-100">{item.name}</td>
                    <td className="px-3 py-2 text-slate-300">
                      {item.item_id || item.detected_item_id || "-"}
                    </td>
                    <td className="max-w-md px-3 py-2 text-xs text-slate-400">
                      {item.analysis_summary || "-"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => importItem(item.id, item.name)}
                        disabled={pending}
                        className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                      >
                        가져오기
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  );
}
