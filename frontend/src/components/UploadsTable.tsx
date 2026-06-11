"use client";

import { useTransition } from "react";

import { actionDeleteDocumentUpload } from "@/lib/actions";
import type { UploadedDocument } from "@/lib/api";
import { useToast } from "./Toast";

type Props = {
  noticeNo: string;
  uploads: UploadedDocument[];
};

export function UploadsTable({ noticeNo, uploads }: Props) {
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  if (uploads.length === 0) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900/30 p-3 text-xs text-slate-400">
        업로드된 파일이 없습니다. "파일 업로드"로 사업자등록증·인감·실적증명 등을 첨부할 수
        있습니다.
      </div>
    );
  }

  const remove = (upload: UploadedDocument) => {
    if (!confirm(`${upload.name}을(를) 삭제하시겠어요?`)) return;
    startTransition(async () => {
      try {
        await actionDeleteDocumentUpload(noticeNo, upload.id);
        toast.push("success", `${upload.name} 삭제`);
      } catch (e) {
        toast.push("error", `삭제 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <div className="overflow-x-auto rounded border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900/80 text-slate-300">
          <tr>
            <th className="px-3 py-2 text-left font-medium">파일</th>
            <th className="px-3 py-2 text-left font-medium">크기</th>
            <th className="px-3 py-2 text-left font-medium">연결 항목</th>
            <th className="px-3 py-2 text-left font-medium">업로드</th>
            <th className="px-3 py-2 text-right font-medium">동작</th>
          </tr>
        </thead>
        <tbody>
          {uploads.map((up) => (
            <tr key={up.id} className="border-t border-slate-800">
              <td className="px-3 py-2 text-slate-100">
                <a
                  href={`/api/notices/${encodeURIComponent(noticeNo)}/documents/uploads/${encodeURIComponent(up.id)}/download`}
                  className="text-brand-400 hover:underline"
                  download={up.name}
                >
                  {up.name}
                </a>
              </td>
              <td className="px-3 py-2 text-slate-300">{formatBytes(up.size)}</td>
              <td className="px-3 py-2 text-slate-300">{up.item_id || "-"}</td>
              <td className="px-3 py-2 text-xs text-slate-400">
                {formatDate(up.uploaded_at)}
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => remove(up)}
                  disabled={pending}
                  className="rounded border border-rose-700 px-2 py-1 text-xs text-rose-200 hover:bg-rose-900/30 disabled:opacity-50"
                >
                  삭제
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  if (!value) return "-";
  try {
    return new Date(value).toISOString().slice(0, 16).replace("T", " ");
  } catch {
    return value;
  }
}
