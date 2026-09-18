"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, RefreshCw, TriangleAlert } from "lucide-react";
import { workspaceApi } from "@/lib/workspace";

export interface Prerequisites {
  input_version: number;
  template_key: string;
  checked_at: string;
  hwp_request_available: boolean;
  required_missing: string[];
  mapping_fields: string[];
  items: {code: string; title: string; state: "checked" | "blocked" | "review"; detail: string;
    action: string; target: "documents" | "writing" | "review" | "company" | "mappings" | "recovery"; blocks_hwp: boolean; requirement_id?: string | null}[];
}

const button = "inline-flex items-center gap-2 border rounded px-3 py-2 text-sm disabled:opacity-40";

export default function WorkspacePrerequisites({prefix, version, template, refreshKey = "", onNavigate, onChecked}: {
  prefix: string; version: number; template: string;
  refreshKey?: string;
  onNavigate: (target: "documents" | "writing" | "review", requirementId?: string | null) => void;
  onChecked: (result: Prerequisites | null) => void;
}) {
  const [result, setResult] = useState<Prerequisites | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const current = useRef({version, template});
  const sequence = useRef(0);
  current.current = {version, template};
  const fresh = result?.input_version === version && result?.template_key === template;
  const check = useCallback(async () => {
    const request = ++sequence.current;
    setBusy(true); setError(""); setResult(null); onChecked(null);
    try {
      const value = await workspaceApi<Prerequisites>(`${prefix}/prerequisites?template_key=${encodeURIComponent(template)}`);
      if (request !== sequence.current) return;
      if (current.current.version !== value.input_version || current.current.template !== value.template_key) {
        setError("입력 또는 템플릿이 변경되었습니다. 다시 점검하세요."); return;
      }
      setResult(value); onChecked(value);
    } catch {
      if (request === sequence.current) setError("필수조건을 조회하지 못했습니다. API 연결을 확인하고 다시 점검하세요.");
    } finally {if (request === sequence.current) setBusy(false);}
  }, [prefix, template, onChecked]);
  useEffect(() => {
    void check();
    return () => {sequence.current += 1;};
  }, [check, version, refreshKey]);
  return <section aria-label="HWP 생성 조건" className="border-y py-3 min-w-0">
    <div className="flex flex-wrap items-center gap-3 py-3">
      <button className={button} disabled={busy} onClick={() => void check()}><RefreshCw size={16}/>{busy ? "점검 중" : "필수조건 다시 확인"}</button>
      <p role="status" aria-label="필수조건 결과" className="text-sm break-words">{busy ? "HWP 생성 조건 점검 중" : error || (fresh && result ? `${new Date(result.checked_at).toLocaleString("ko-KR")} · ${result.hwp_request_available ? "HWP 초안 요청 조건 확인 · 제출 준비는 별도 검토" : "HWP 생성 전 보완 필요"}` : "현재 입력과 선택한 HWP 템플릿을 점검하세요.")}</p>
    </div>
    {fresh && result && result.items.filter(item=>item.blocks_hwp).map(item=><p key={item.code} className="text-sm text-red-700 mb-2">{item.title}: {item.detail}</p>)}
    <details ref={detailsRef}>
    <summary className="font-semibold text-sm cursor-pointer">필수조건 점검 · {template === "proposal_layout_v1" ? "제안서 · 실무 서식" : template === "proposal" ? "제안서" : "입찰참가신청서"}</summary>
    {fresh && result && <>
      <ul className="divide-y">{result.items.map(item => <li key={item.code} className="py-3 flex flex-wrap items-start gap-3">
        {item.state === "checked" ? <CheckCircle2 size={18} className="text-green-700 shrink-0 mt-1"/> : <TriangleAlert size={18} className="text-amber-700 shrink-0 mt-1"/>}
        <div className="min-w-0 flex-1 basis-48"><h3 className="text-sm font-medium break-words">{item.title} · {item.state === "checked" ? "확인" : item.state === "review" ? "생성 후 검토" : "보완 필요"}</h3><p className="text-sm text-gray-600 break-words">{item.detail}</p>{item.blocks_hwp && <p className="text-xs text-red-700 mt-1">HWP 생성 차단</p>}</div>
        {item.target === "company" || item.target === "mappings" ? <Link className="text-sm underline" href={`/admin#${item.target}`}>{item.action}</Link> : item.target === "recovery" ? <details className="w-full text-sm"><summary className="cursor-pointer underline">복구 절차 확인</summary><ol className="list-decimal pl-5 space-y-2 mt-2"><li>한글 창의 보안 안내·오류와 기존 생성 파일을 사람이 확인합니다.</li><li>HWP Worker를 정상 종료한 뒤 관리자가 복구 기록을 확인하고 확인 의견을 남깁니다.</li><li>Worker를 다시 실행한 뒤 필수조건을 재점검합니다.</li></ol></details> : <button className="inline-flex items-center gap-1 text-sm underline" onClick={() => {if (detailsRef.current) detailsRef.current.open = false; onNavigate(item.target as "documents" | "writing" | "review", item.requirement_id);}}>{item.action}<ArrowRight size={14}/></button>}
      </li>)}</ul>
      {!!result.mapping_fields.length && <details className="border-t py-3 text-sm"><summary className="cursor-pointer">템플릿에 필요한 필드명 {result.mapping_fields.length}개</summary><ul className="mt-2 grid sm:grid-cols-2 gap-2">{result.mapping_fields.map(field => <li key={field} className="break-all font-mono">{field}</li>)}</ul></details>}
    </>}
  </details></section>;
}
