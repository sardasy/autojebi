"use client";

import { useState, useTransition } from "react";

import { actionIngestSkus } from "@/lib/actions";
import { useToast } from "./Toast";

/**
 * ABB SKU 카탈로그 → Qdrant 인제스트 (M3, 1회성 어드민).
 * source 비우면 data/abb_catalog_sample.json 기본 사용.
 */
export function SkuIngestButton() {
  const [source, setSource] = useState("");
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const submit = () => {
    setResultMessage(null);
    startTransition(async () => {
      try {
        const r = await actionIngestSkus(source ? { source } : {});
        const message = `Qdrant 인제스트 완료 — ${r.ingested}개 SKU (컬렉션: ${r.collection})`;
        setResultMessage(message);
        toast.push(
          "success",
          message,
        );
      } catch (e) {
        const message = `인제스트 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="block text-xs text-slate-400 mb-1">
          source 파일 경로 (비우면 <code className="bg-slate-800 px-1 rounded">data/abb_catalog_sample.json</code>)
        </span>
        <input
          type="text"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="data/abb_catalog_sample.json"
          className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm font-mono"
        />
      </label>
      <button
        type="button"
        onClick={submit}
        disabled={pending}
        className="rounded bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {pending ? "인제스트 중…" : "Qdrant에 인제스트"}
      </button>
      {resultMessage ? (
        <div role="status" className="text-xs text-slate-300">
          {resultMessage}
        </div>
      ) : null}
    </div>
  );
}
