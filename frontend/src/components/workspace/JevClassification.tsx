"use client";

import {useCallback, useEffect, useState} from "react";
import {workspaceApi, jobStates, type Workspace, type WorkspaceJob} from "@/lib/workspace";
import {buttonClass, type Mutate} from "./ui";

type Signal = {value: string; confidence: number; probabilities: Record<string, number>};
type Evaluation = {
  notice_no: string; input_hash: string;
  decision: {engine_name: string; model_version: string; policy_version: string;
    product_family: Signal; application: Signal; company_relevance: Signal; bid_priority: Signal};
  routing: {target: string; overall_confidence: number; limiting_signal: string; reason: string};
};
type ClassificationJob = Omit<WorkspaceJob, "result"> & {
  result: {evaluation?: Evaluation; decision_id?: string} | null;
};
type State = {visible: boolean; enabled: boolean; message: string; request_hash: string | null;
  policy_version: string | null; model: string | null; current_job_id: string | null;
  history: ClassificationJob[]};
const signals = {product_family: "제품군", application: "적용 분야", company_relevance: "회사 관련도", bid_priority: "검토 우선순위"} as const;
const labels: Record<string, string> = {hil: "HIL", hvdc: "HVDC", ess: "ESS", ev: "전기차", railway: "철도", renewable: "재생에너지", grid: "전력망", industrial: "산업", defense: "방산", research: "연구", high: "높음", medium: "보통", low: "낮음", urgent: "긴급", none: "없음", irrelevant: "관련 없음", other: "기타", mixed: "복합", simulation_software: "시뮬레이션 소프트웨어", semiconductor: "전력반도체", fuse: "퓨즈", capacitor: "커패시터", busbar: "부스바", sensor: "센서", power_equipment: "전력 장비"};
const routes: Record<string, string> = {auto_process: "후속 처리 검토", llm_verify: "추가 분석 검토", human_review: "담당자 검토"};

export default function JevClassification({ws, prefix, busy, mutate}: {
  ws: Workspace; prefix: string; busy: boolean; mutate: Mutate;
}) {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      const next = await workspaceApi<State>(`${prefix}/classification`);
      if (Array.isArray(next.history)) {setState(next); setError("");}
    } catch {setError("JEV 분류 상태를 불러오지 못했습니다. 새로고침하세요.");}
  }, [prefix]);
  useEffect(() => {void refresh();}, [refresh, ws]);
  if (!state?.visible) return error ? <p role="status" className="text-sm">{error}</p> : null;
  const current = state.history.find(job => job.id === state.current_job_id);
  const pending = current && ["queued", "running"].includes(current.status);
  const failed = current && ["failed", "blocked"].includes(current.status);
  return <section aria-label="JEV 공고 분류" className="border-y py-4 space-y-3">
    <h2 className="font-semibold">JEV 공고 분류</h2>
    <p className="text-sm">{state.message} 참가 결정과 제출 승인은 담당자가 별도로 확인합니다.</p>
    {state.policy_version && <p className="text-xs text-gray-600">회사 정책: {state.policy_version} · 요청 모델: {state.model}</p>}
    {error && <p role="alert">{error}</p>}
    <button className={buttonClass} disabled={busy || !state.enabled || !!pending || !!failed || !!error || ws.source_changed}
      onClick={() => void mutate(`${prefix}/jobs`, {kind: "jev", input_version: ws.version,
        idempotency_key: crypto.randomUUID(), classification_hash: state.request_hash}, "JEV 분류 접수")}>
      {pending ? "JEV 분류 실행 중" : current?.status === "succeeded" ? "JEV 결과 다시 확인" : "JEV 분류 실행"}
    </button>
    {failed && <p role="status" className="text-sm text-red-700">미평가 · {current.error?.message} 동일 요청의 실패 기록을 보존하며 재호출하지 않습니다.</p>}
    {!current && state.history.length > 0 && <p className="text-sm text-amber-800">현재 원문·정책의 분류 결과가 없습니다. 이전 결과는 이력으로 보존됩니다.</p>}
    {state.history.map(job => {
      const evaluation = job.status === "succeeded" ? job.result?.evaluation : null;
      return <details key={job.id} open={job.id === state.current_job_id} className="border-t pt-2">
        <summary className="text-sm cursor-pointer">{job.id === state.current_job_id ? "현재 원문·정책 기준" : "이전 원문·정책 기준"} · 입력 버전 {job.input_version} · {jobStates[job.status]}</summary>
        {evaluation ? <div className="space-y-2 pt-2">
          <div className="overflow-x-auto"><table className="text-sm w-full"><thead><tr className="text-left"><th>분류 항목</th><th>결과</th><th>API 신뢰도</th></tr></thead>
            <tbody>{Object.entries(signals).map(([key, label]) => {const signal = evaluation.decision[key as keyof typeof signals];
              return <tr key={key}><th className="text-left py-1">{label}</th><td>{labels[signal.value] || signal.value}</td><td>{Math.round(signal.confidence * 100)}%</td></tr>;
            })}</tbody></table></div>
          <p className="text-sm">검토 안내: {routes[evaluation.routing.target]} · 최저 신뢰도 {Math.round(evaluation.routing.overall_confidence * 100)}%</p>
          <p className="text-xs break-all">응답 모델: {evaluation.decision.model_version} · 정책: {evaluation.decision.policy_version}</p>
          <p className="text-xs break-all">저장 기록: {job.result?.decision_id || "확인 중"}</p>
        </div> : <p className="text-sm pt-2">{job.error ? `미평가 · ${job.error.message}` : "분류 결과 대기 중"}</p>}
      </details>;
    })}
  </section>;
}
