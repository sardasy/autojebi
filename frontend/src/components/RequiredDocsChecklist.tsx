"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";

import {
  actionUpdateDocumentChecklistItem,
  actionUploadDocument,
} from "@/lib/actions";
import type { DocumentChecklistItem, DocumentItemStatus } from "@/lib/api";
import { DocSourceBadge } from "./DocSourceBadge";
import { useToast } from "./Toast";

// 보조 목록이므로 "필수(빨강)" 톤을 쓰지 않는다. 미준비는 amber로만 표기.
const STATUS_META: Record<
  DocumentItemStatus,
  { label: string; cls: string; ready: boolean }
> = {
  ready: { label: "준비됨", cls: "border-emerald-700 bg-emerald-950/40 text-emerald-200", ready: true },
  generated: { label: "생성됨", cls: "border-emerald-700 bg-emerald-950/40 text-emerald-200", ready: true },
  not_applicable: { label: "후보", cls: "border-slate-700 bg-slate-900 text-slate-400", ready: true },
  blocked: { label: "보류", cls: "border-slate-700 bg-slate-900 text-slate-400", ready: false },
  needed: { label: "확인 필요", cls: "border-amber-700 bg-amber-950/30 text-amber-200", ready: false },
};

type Category = "confirm" | "common" | "reference";

function categoryOf(item: DocumentChecklistItem): Category {
  if (item.document_role === "reference_only") return "reference";
  if (item.type === "company_common" || item.document_role === "internal_prep") return "common";
  return "confirm";
}

const CATEGORY_META: Record<Category, { title: string; hint: string }> = {
  confirm: { title: "추가 확인 항목", hint: "공고/규격에서 추정된 항목 — 해당되면 준비하세요." },
  common: { title: "회사 공통 후보", hint: "회사가 보통 갖춰두는 서류 — 공고 필수가 아닙니다." },
  reference: { title: "검토 원문(참고)", hint: "제출서류가 아니라 읽고 검토할 첨부 원문입니다." },
};

function ChecklistRow({ noticeNo, item }: { noticeNo: string; item: DocumentChecklistItem }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);
  const meta = STATUS_META[item.status] ?? STATUS_META.needed;
  const isReference = item.document_role === "reference_only";

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
    <li className="flex items-center gap-2 rounded border border-slate-800 bg-slate-900/30 p-2.5">
      {!isReference ? (
        <span className={`shrink-0 rounded border px-2 py-0.5 text-[11px] ${meta.cls}`}>
          {meta.label}
        </span>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-slate-200">{item.name}</div>
        {item.reason ? (
          <div className="mt-0.5 truncate text-xs text-slate-500">{item.reason}</div>
        ) : null}
      </div>
      <DocSourceBadge origin={{ kind: "checklist", source: item.source, type: item.type }} />
      {!isReference && !meta.ready ? (
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
            className="rounded border border-slate-600 px-2 py-0.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {pending ? "처리 중…" : "업로드"}
          </button>
          <button
            type="button"
            onClick={markReady}
            disabled={pending}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            준비완료
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
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">표시할 보조 준비서류가 없습니다.</p>;
  }
  const groups: Record<Category, DocumentChecklistItem[]> = {
    confirm: [],
    common: [],
    reference: [],
  };
  for (const item of items) groups[categoryOf(item)].push(item);

  return (
    <div className="space-y-3">
      {(["confirm", "common", "reference"] as Category[])
        .filter((c) => groups[c].length > 0)
        .map((c) => (
          <div key={c}>
            <div className="mb-1 flex items-baseline gap-2">
              <span className="text-xs font-semibold text-slate-300">
                {CATEGORY_META[c].title}
              </span>
              <span className="text-[11px] text-slate-500">{CATEGORY_META[c].hint}</span>
            </div>
            <ul className="space-y-1.5">
              {groups[c].map((item) => (
                <ChecklistRow key={item.id} noticeNo={noticeNo} item={item} />
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}
