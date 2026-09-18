"use client";

import { useEffect, useState } from "react";
import { workspaceApi } from "@/lib/workspace";

type CodeVersion = {loaded_fingerprint: string | null; disk_fingerprint: string | null; status: "current" | "mismatch" | "unknown"; restart_required: boolean};
type Health = {available: boolean; state: string; heartbeat_at: string | null; last_failure: {code: string; at: string} | null; lanes?: Record<string, Health>; runtime?: {api: CodeVersion; workers: Record<string, CodeVersion>; status: string; restart_required: boolean; diagnostics: {component: string; code: string; restart_required: boolean}[]}};
const states: Record<string, string> = {starting: "시작 중", idle: "대기", recovering: "결과 복구 중", executing: "실행 중", persisting: "결과 저장 중", retrying: "연결 복구 중", stopped: "중지", unknown: "확인되지 않음"};
const components: Record<string, string> = {api: "API", "worker:local": "로컬 문서 실행기", "worker:external": "외부 연동 실행기", "worker:all": "작업 실행기"};

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
  const versions: [string, CodeVersion][] = health?.runtime ? [
    ["api", health.runtime.api],
    ...Object.entries(health.runtime.workers).map(([lane, version]): [string, CodeVersion] => [`worker:${lane}`, version]),
  ] : [];
  return <div aria-label="작업 실행기 상태" aria-live="polite" className="border-b pb-2 text-sm space-y-1">
    <p>작업 실행기 · {health?.available ? states[health.state] || "응답 중" : "응답 확인 필요"}{health?.heartbeat_at ? ` · ${new Date(health.heartbeat_at).toLocaleTimeString("ko-KR")}` : ""}</p>
    {!health?.available && <p className="text-amber-800">작업 실행기 연결을 확인하세요. 접수된 작업은 보존됩니다.</p>}
    {health?.lanes && Object.entries(health.lanes).map(([lane, value]) => <p key={lane}>{lane === "local" ? "로컬 문서" : "외부 연동"} · {value.available ? states[value.state] || "응답 중" : "응답 확인 필요"}</p>)}
    {health?.runtime?.restart_required && <p role="status" className="text-amber-800">수정된 코드가 실행 중인 프로그램에 반영되지 않았습니다. 진행 중인 작업이 끝난 뒤 아래 프로세스를 재시작하세요.</p>}
    {health?.runtime?.diagnostics.map(item => <p key={item.component} className="text-amber-800">
      {components[item.component] || "실행 프로세스"} · {item.restart_required ? "코드 변경 반영을 위한 재시작 필요" : "실행 코드 버전 확인 필요"}
    </p>)}
    {health?.runtime && <details><summary>실행 코드 버전</summary>
      {versions.map(([component, version]) => <p key={component}>{components[component] || "실행 프로세스"} · 시작 시 {version.loaded_fingerprint?.slice(0, 12) || "확인 불가"} · 현재 파일 {version.disk_fingerprint?.slice(0, 12) || "확인 불가"}</p>)}
    </details>}
    {health?.last_failure && <details><summary>이전 연결 오류</summary><p>{health.last_failure.code} · {new Date(health.last_failure.at).toLocaleString("ko-KR")}</p></details>}
  </div>;
}
