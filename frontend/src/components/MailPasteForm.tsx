"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { actionExtractMail } from "@/lib/actions";
import type { MailExtractResponse } from "@/lib/api";
import { useToast } from "./Toast";

export function MailPasteForm() {
  const [rawText, setRawText] = useState("");
  const [source, setSource] = useState("KJEBI");
  const [result, setResult] = useState<MailExtractResponse | null>(null);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const submit = () => {
    if (!rawText.trim()) {
      toast.push("error", "메일 본문이 비어 있습니다");
      return;
    }
    startTransition(async () => {
      try {
        const r = await actionExtractMail({ raw_text: rawText, source });
        setResult(r);
        if (r.upserted) {
          toast.push(
            "success",
            `등록 완료 — ${r.upserted.notice_no} (confidence ${r.confidence.toFixed(2)})`,
          );
        } else {
          toast.push(
            "info",
            `notice_no 추출 실패 — 본문을 확인하세요 (errors: ${r.errors.join("; ") || "none"})`,
          );
        }
      } catch (e) {
        toast.push("error", `추출 실패: ${(e as Error).message}`);
      }
    });
  };

  const clear = () => {
    setRawText("");
    setResult(null);
  };

  return (
    <div className="space-y-3">
      <label className="block">
        <span className="mb-1 block text-xs text-slate-400">메일 본문 (KJEBI 알림메일 통째로 paste)</span>
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          rows={10}
          placeholder={"□ 공고번호 : R26BK01543282-000\n□ 공고명 : ...\n□ 마감일시 : 2026-06-20 18:00\n..."}
          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs font-mono"
          spellCheck={false}
        />
      </label>
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">source</span>
          <input
            type="text"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="w-32 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm"
          />
        </label>
        <button
          type="button"
          onClick={submit}
          disabled={pending}
          className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {pending ? "추출 중…" : "추출 & 등록"}
        </button>
        {rawText || result ? (
          <button
            type="button"
            onClick={clear}
            disabled={pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            초기화
          </button>
        ) : null}
      </div>

      {result ? (
        <div className="space-y-2 rounded border border-slate-700 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">
              confidence{" "}
              <span className="font-mono text-slate-100">{result.confidence.toFixed(2)}</span>
            </span>
            {result.upserted ? (
              <Link
                href={`/notices/${encodeURIComponent(result.upserted.notice_no)}`}
                className="text-brand-300 hover:text-brand-200 underline"
              >
                /notices/{result.upserted.notice_no} →
              </Link>
            ) : (
              <span className="text-amber-400">미등록 (notice_no 없음)</span>
            )}
          </div>
          <dl className="grid grid-cols-1 gap-1 text-xs md:grid-cols-2">
            <ExtractField label="notice_no" value={result.extracted.notice_no} />
            <ExtractField label="title" value={result.extracted.title} />
            <ExtractField label="org_name" value={result.extracted.org_name} />
            <ExtractField label="close_date" value={result.extracted.close_date} />
            <ExtractField
              label="base_price"
              value={result.extracted.base_price?.toLocaleString() ?? null}
            />
            <ExtractField label="bid_url" value={result.extracted.bid_url} />
            <ExtractField label="summary" value={result.extracted.summary} />
          </dl>
          {result.errors.length > 0 ? (
            <p className="text-xs text-red-400">
              ⚠ {result.errors.join("; ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ExtractField({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-slate-500">{label}</dt>
      <dd className={`font-mono ${value ? "text-slate-100" : "text-slate-600"}`}>
        {value ?? "—"}
      </dd>
    </div>
  );
}
