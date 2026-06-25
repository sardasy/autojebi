"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";

import {
  actionUpdateDocumentChecklistItem,
  actionUploadDocument,
} from "@/lib/actions";
import type { DocumentChecklistItem, DocumentItemStatus } from "@/lib/api";
import { useToast } from "./Toast";

const STATUS_META: Record<
  DocumentItemStatus,
  { label: string; cls: string; ready: boolean }
> = {
  ready: { label: "준비됨", cls: "border-emerald-700 bg-emerald-950/40 text-emerald-200", ready: true },
  generated: { label: "생성됨", cls: "border-emerald-700 bg-emerald-950/40 text-emerald-200", ready: true },
  not_applicable: { label: "해당없음", cls: "border-slate-700 bg-slate-900 text-slate-400", ready: true },
  blocked: { label: "확인 필요", cls: "border-amber-700 bg-amber-950/30 text-amber-200", ready: false },
  needed: { label: "필요", cls: "border-rose-700 bg-rose-950/30 text-rose-200", ready: false },
};

function ChecklistRow({ noticeNo, item }: { noticeNo: string; item: DocumentChecklistItem }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);
  const meta = STATUS_META[item.status] ?? STATUS_META.needed;

  const upload = (file: File) => {
    start(async () => {
      try {
        await actionUploadDocument(noticeNo, file, item.id);
        toast.push("success", `${item.name} 업로드 완료`);
        router.refresh();
      } catch (e) {
        toast.push("error", `업로드 실패: ${(e as Error).message}`);
      }
    });
  };

  const markReady = () => {
    start(async () => {
      try {
        await actionUpdateDocumentChecklistItem(noticeNo, item.id, { status: "ready" });
        router.refresh();
      } catch (e) {
        toast.push("error", `상태 변경 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <li className="flex items-center gap-3 rounded border border-slate-800 bg-slate-900/40 p-3">
      <span className={`shrink-0 rounded border px-2 py-1 text-xs ${meta.cls}`}>
        {meta.label}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-slate-100">{item.name}</div>
        {item.reason ? (
          <div className="mt-0.5 truncate text-xs text-slate-500">{item.reason}</div>
        ) : null}
      </div>
      {!meta.ready ? (
        <div className="flex shrink-0 items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={pending}
            className="rounded bg-brand-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {pending ? "처리 중…" : "파일 업로드"}
          </button>
          <button
            type="button"
            onClick={markReady}
            disabled={pending}
            className="rounded border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            준비완료 표시
          </button>
        </div>
      ) : null}
    </li>
  );
}

export function RequiredDocsChecklist({
  noticeNo,
  items,
}: {
  noticeNo: string;
  items: DocumentChecklistItem[];
}) {
  const required = items.filter((i) => i.required);
  if (required.length === 0) {
    return <p className="text-sm text-slate-500">필수 서류가 없습니다.</p>;
  }
  return (
    <ul className="space-y-2">
      {required.map((item) => (
        <ChecklistRow key={item.id} noticeNo={noticeNo} item={item} />
      ))}
    </ul>
  );
}
