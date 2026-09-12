"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { workspaceApi } from "@/lib/workspace";

type LlmSettings = {
  llm: {provider: "anthropic" | "gemini" | "openai"; model: string; key_registered: boolean; connection_status: "not_checked"};
};

export default function WorkspaceLlmStatus() {
  const [value, setValue] = useState<LlmSettings | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let mounted = true;
    setBusy(true);
    setError(false);
    setValue(null);
    workspaceApi<LlmSettings>("/settings").then(result => {
      if (mounted) setValue(result);
    }).catch(() => {if (mounted) setError(true);})
      .finally(() => {if (mounted) setBusy(false);});
    return () => {mounted = false;};
  }, [revision]);
  return <section aria-label="AI 분석 설정" className="mt-4 border-t border-gray-200 pt-4 text-sm">
    <div className="flex items-center gap-3">
      <h2 className="font-semibold">AI 분석</h2>
      <button type="button" aria-label="AI 설정 새로고침" title="AI 설정 새로고침" disabled={busy}
        className="flex h-8 w-8 items-center justify-center rounded border disabled:opacity-50"
        onClick={() => setRevision(n => n + 1)}><RefreshCw size={16}/></button>
    </div>
    <div role="status" className="mt-2 space-y-1">
      {busy && <p>설정 확인 중</p>}
      {error && <p className="text-red-800">AI 설정을 조회하지 못했습니다. API 연결 후 다시 확인하세요.</p>}
      {value?.llm && <>
        <p className="break-words">{{gemini: "Google Gemini", anthropic: "Claude", openai: "OpenAI"}[value.llm.provider]} · {value.llm.model}</p>
        <p className={value.llm.key_registered ? "text-gray-700" : "text-amber-800"}>
          {value.llm.key_registered ? "키 등록됨 · 실제 연결은 분석 실행 결과에서 확인 필요" : "키 미등록 · 분석 실행 불가"}
        </p>
      </>}
    </div>
  </section>;
}
