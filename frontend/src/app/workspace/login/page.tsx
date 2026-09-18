"use client";

import Link from "next/link";
import {useState} from "react";
import {workspaceSessionFetch} from "@/lib/workspace";

export default function WorkspaceLogin() {
  const [token, setToken] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState("");
  return <main className="max-w-md mx-auto p-6 space-y-5">
    <h1 className="text-xl font-semibold">작업대 개인 로그인</h1>
    <p className="text-sm">관리자가 발급한 개인 인증 토큰으로 로그인하세요. 작성·검토·최종 승인 권한과 기록에 개인 계정이 적용됩니다.</p>
    <form className="space-y-4" onSubmit={async event => {
      event.preventDefault(); if (!token || pending) return;
      setPending(true); setStatus("");
      try {
        const response = await workspaceSessionFetch("POST", {token});
        setToken("");
        if (!response.ok) {
          const body = await response.json();
          setStatus(body.detail?.message || "로그인하지 못했습니다."); setPending(false); return;
        }
        window.location.assign("/workspace");
      } catch {setToken(""); setStatus("개인 인증 서버에 연결할 수 없습니다."); setPending(false);}
    }}>
      <label className="block text-sm">개인 인증 토큰<input name="token" type="password" autoComplete="current-password" required minLength={32} maxLength={512} value={token} onChange={event => setToken(event.target.value)} className="block w-full border rounded p-2 mt-1"/></label>
      <button type="submit" disabled={!token || pending} className="border rounded px-4 py-2 disabled:opacity-40">{pending ? "로그인 중" : "로그인"}</button>
      {status && <p role="alert" className="text-sm text-red-700">{status}</p>}
    </form>
    <Link href="/workspace" className="text-sm underline">작업대로 돌아가기</Link>
  </main>;
}
