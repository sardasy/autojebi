"use client";

import { useMemo, useState, useTransition } from "react";

import { actionUpsert } from "@/lib/actions";
import { useToast } from "./Toast";

export function UpsertNoticeForm() {
  const [noticeNo, setNoticeNo] = useState("TEST-001");
  const [title, setTitle] = useState("Typhoon HIL test procurement");
  const [source, setSource] = useState("KJEBI");
  const [rawText, setRawText] = useState(`{\n  "from": "manual"\n}`);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const rawValidation = useMemo(() => {
    if (!rawText.trim()) return { ok: true, parsed: null as Record<string, unknown> | null };
    try {
      const parsed = JSON.parse(rawText);
      if (typeof parsed !== "object" || Array.isArray(parsed)) {
        return { ok: false, error: "raw는 JSON 객체여야 합니다", parsed: null };
      }
      return { ok: true, parsed: parsed as Record<string, unknown> };
    } catch (e) {
      return { ok: false, error: (e as Error).message, parsed: null };
    }
  }, [rawText]);

  const submit = () => {
    if (!noticeNo.trim()) {
      toast.push("error", "notice_no가 필요합니다");
      return;
    }
    if (!rawValidation.ok) {
      toast.push("error", `raw JSON 파싱 실패: ${rawValidation.error}`);
      return;
    }
    startTransition(async () => {
      try {
        const r = await actionUpsert({
          notice_no: noticeNo,
          title: title || undefined,
          source: source || undefined,
          raw: rawValidation.parsed ?? undefined,
        });
        toast.push("success", `Upsert 완료 — status: ${r.status}, fit_score: ${r.fit_score}`);
      } catch (e) {
        toast.push("error", `Upsert 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Field label="notice_no">
          <input
            type="text"
            value={noticeNo}
            onChange={(e) => setNoticeNo(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm font-mono"
          />
        </Field>
        <Field label="title">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm"
          />
        </Field>
        <Field label="source">
          <input
            type="text"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm"
          />
        </Field>
      </div>
      <Field label="raw (JSON)">
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          rows={6}
          className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono"
          spellCheck={false}
        />
      </Field>
      {!rawValidation.ok ? (
        <p className="text-xs text-red-400">⚠ {rawValidation.error}</p>
      ) : null}
      <button
        type="button"
        onClick={submit}
        disabled={pending}
        className="rounded bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {pending ? "Upsert 중…" : "Upsert 실행"}
      </button>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-slate-400 mb-1">{label}</span>
      {children}
    </label>
  );
}
