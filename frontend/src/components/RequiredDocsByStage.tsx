"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { actionCheckRequiredDocument } from "@/lib/actions";
import type {
  NoticeRequiredDocument,
  RequirementType,
  SubmitStage,
} from "@/lib/api";
import { useToast } from "./Toast";

const STAGE_LABEL: Record<SubmitStage, string> = {
  bid: "입찰 시 제출",
  proposal: "제안서 제출 시",
  price: "가격입찰 시",
  conditional: "조건부 제출",
  post_award: "낙찰 후 제출",
  contract: "계약 후 제출",
  delivery: "납품 단계 제출",
};

const STAGE_ORDER: SubmitStage[] = [
  "bid",
  "proposal",
  "price",
  "conditional",
  "post_award",
  "contract",
  "delivery",
];

// "지금 준비"에 해당하는 단계는 펼쳐서, 낙찰후/계약후는 접어서 노출
const NOW_STAGES = new Set<SubmitStage>(["bid", "proposal", "price", "conditional"]);

const TYPE_META: Record<RequirementType, { label: string; cls: string }> = {
  required: { label: "필수", cls: "border-rose-700 bg-rose-950/30 text-rose-200" },
  conditional: { label: "조건부", cls: "border-amber-700 bg-amber-950/30 text-amber-200" },
  winner_only: { label: "낙찰자", cls: "border-sky-700 bg-sky-950/30 text-sky-200" },
  contract_stage: { label: "계약단계", cls: "border-slate-600 bg-slate-900 text-slate-300" },
  reference: { label: "참고", cls: "border-slate-700 bg-slate-900 text-slate-400" },
};

function DocRow({ noticeNo, doc }: { noticeNo: string; doc: NoticeRequiredDocument }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [open, setOpen] = useState(false);
  const meta = TYPE_META[doc.requirement_type] ?? TYPE_META.required;

  const toggle = () => {
    start(async () => {
      try {
        await actionCheckRequiredDocument(noticeNo, doc.id, { checked: !doc.checked });
        router.refresh();
      } catch (e) {
        toast.push("error", `확인 상태 변경 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <li className="rounded border border-slate-800 bg-slate-900/40 p-3">
      <div className="flex items-center gap-3">
        <input
          type="checkbox"
          checked={doc.checked}
          onChange={toggle}
          disabled={pending}
          className="h-4 w-4 shrink-0 accent-brand-500"
          aria-label={`${doc.doc_name} 확인`}
        />
        <span className={`shrink-0 rounded border px-2 py-0.5 text-xs ${meta.cls}`}>
          {meta.label}
        </span>
        <span className={`min-w-0 flex-1 truncate text-sm ${doc.checked ? "text-slate-500 line-through" : "text-slate-100"}`}>
          {doc.doc_name}
        </span>
        <span className="shrink-0 text-xs text-slate-500">
          {Math.round((doc.confidence || 0) * 100)}%
        </span>
        {doc.evidence_text ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="shrink-0 rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            근거
          </button>
        ) : null}
      </div>
      {open && doc.evidence_text ? (
        <div className="mt-2 rounded bg-slate-950/60 p-2 text-xs text-slate-300">
          <p className="whitespace-pre-wrap">“{doc.evidence_text}”</p>
          <p className="mt-1 text-slate-500">
            {doc.source_file || "첨부"}
            {doc.page_no ? ` · p.${doc.page_no}` : ""}
            {doc.deadline ? ` · ${doc.deadline}` : ""}
            {doc.condition ? ` · 조건: ${doc.condition}` : ""}
          </p>
        </div>
      ) : null}
    </li>
  );
}

function StageGroup({
  noticeNo,
  stage,
  docs,
}: {
  noticeNo: string;
  stage: SubmitStage;
  docs: NoticeRequiredDocument[];
}) {
  const now = NOW_STAGES.has(stage);
  const header = (
    <span className="text-sm font-semibold text-slate-200">
      {STAGE_LABEL[stage]}{" "}
      <span className="text-xs font-normal text-slate-500">({docs.length})</span>
    </span>
  );
  return (
    <details open={now} className="rounded border border-slate-800 bg-slate-900/20 p-3">
      <summary className="cursor-pointer select-none">{header}</summary>
      <ul className="mt-3 space-y-2">
        {docs.map((d) => (
          <DocRow key={d.id} noticeNo={noticeNo} doc={d} />
        ))}
      </ul>
    </details>
  );
}

export function RequiredDocsByStage({
  noticeNo,
  items,
}: {
  noticeNo: string;
  items: NoticeRequiredDocument[];
}) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        첨부문서에서 제출서류를 추출하지 못했습니다. 첨부가 없거나 텍스트 추출이 어려운 문서일 수 있습니다.
      </p>
    );
  }
  const grouped = new Map<SubmitStage, NoticeRequiredDocument[]>();
  for (const it of items) {
    const arr = grouped.get(it.submit_stage) || [];
    arr.push(it);
    grouped.set(it.submit_stage, arr);
  }
  return (
    <div className="space-y-3">
      {STAGE_ORDER.filter((s) => grouped.has(s)).map((stage) => (
        <StageGroup
          key={stage}
          noticeNo={noticeNo}
          stage={stage}
          docs={grouped.get(stage)!}
        />
      ))}
    </div>
  );
}
