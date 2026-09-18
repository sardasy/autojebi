"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import type {WorkspaceIdentity as Identity} from "@/lib/workspace-session";

const roles = {viewer: "조회자", writer: "작성자", reviewer: "검토자", approver: "최종 승인자"};

export default function WorkspaceIdentity() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [status, setStatus] = useState("개인 인증 확인 중");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    fetch("/api/workspace-session", {cache: "no-store"}).then(async response => {
      if (!active) return;
      if (!response.ok) {setStatus(response.status === 401 ? "로그인이 필요합니다." : "개인 인증 연결을 확인하세요."); return;}
      const value = await response.json() as Identity;
      if (active) {setIdentity(value); setStatus("");}
    }).catch(() => {if (active) setStatus("개인 인증 연결을 확인하세요.");});
    return () => {active = false;};
  }, []);
  return <aside aria-label="개인 계정" className="flex flex-wrap items-center gap-3 text-sm">
    {identity?.actor ? <><span>{identity.actor.name} · {roles[identity.actor.role]}</span>
      <button type="button" disabled={busy} className="border rounded px-3 py-1 disabled:opacity-40" onClick={async () => {
        setBusy(true);
        try {
          const response = await fetch("/api/workspace-session", {method: "DELETE"});
          if (!response.ok) throw new Error();
          window.location.assign("/workspace/login");
        } catch {setStatus("로그아웃하지 못했습니다. 다시 시도하세요."); setBusy(false);}
      }}>로그아웃</button></> : identity && !identity.enabled ? <span>개발 모드 · 개인 인증 꺼짐</span> : <Link href="/workspace/login" className="underline">개인 계정 로그인</Link>}
    {!!status && <span role="status">{status}</span>}
  </aside>;
}
