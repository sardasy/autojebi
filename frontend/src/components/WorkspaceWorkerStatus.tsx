"use client";

import { useEffect, useState } from "react";
import { workspaceApi } from "@/lib/workspace";

type Health = {available: boolean; state: string; heartbeat_at: string | null; last_failure: {code: string; at: string} | null; lanes?: Record<string, Health>};
const states: Record<string, string> = {starting: "시작 중", idle: "대기", recovering: "결과 복구 중", executing: "실행 중", persisting: "결과 저장 중", retrying: "연결 복구 중", stopped: "중지", unknown: "확인되지 않음"};

export default function WorkspaceWorkerStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let mounted = true;
    async function check() {
      try {const value = await workspaceApi<Health>("/worker/health"); if (mounted) setHealth(value);}
      catch {if (mounted) setHealth(null);}
    }
    void check();
    const timer = setInterval(() => void check(), 10000);
    return () => {mounted = false; clearInterval(timer);};
  }, []);
  return <div aria-label="작업 실행기 상태" aria-live="polite" className="border-b pb-2 text-sm space-y-1">
    <p>작업 실행기 · {health?.available ? states[health.state] || "응답 중" : "응답 확인 필요"}{health?.heartbeat_at ? ` · ${new Date(health.heartbeat_at).toLocaleTimeString("ko-KR")}` : ""}</p>
    {!health?.available && <p className="text-amber-800">작업 실행기 연결을 확인하세요. 접수된 작업은 보존됩니다.</p>}
    {health?.lanes && Object.entries(health.lanes).map(([lane, value]) => <p key={lane}>{lane === "local" ? "로컬 문서" : "외부 연동"} · {value.available ? states[value.state] || "응답 중" : "응답 확인 필요"}</p>)}
    {health?.last_failure && <details><summary>이전 연결 오류</summary><p>{health.last_failure.code} · {new Date(health.last_failure.at).toLocaleString("ko-KR")}</p></details>}
  </div>;
}
