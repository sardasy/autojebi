"use client";
import {useEffect, useRef, useState} from "react";
import {pollHwpHealth, type HwpHealthState} from "@/lib/hwpHealth";

const states: Record<string, string> = {worker_connected: "연결됨", worker_running: "작업 중", worker_recovery: "복구 필요", worker_timeout: "응답 지연", worker_offline: "연결 안 됨", worker_token_missing: "인증 설정 필요", worker_auth: "인증 실패"};
const stages: Record<string, string> = {starting: "시작", mutex: "다른 작업 확인", initialize: "COM 초기화", dispatch: "한글 활성화", visibility: "창 준비", document: "문서 준비", field: "입력 필드 생성", table: "표 작성", layout: "서식 작성", font: "글꼴 설정", paragraph: "문단 설정", page_setup: "용지 설정", page_number: "쪽번호 설정", open: "문서 열기", enumerate: "필드 검사", write: "값 입력", save: "저장", reopen: "다시 열기", readback: "저장값 대조", page_images: "페이지 이미지 생성", close: "문서 닫기", quit: "한글 종료"};
export default function WorkspaceHwpStatus() {
  const [health, setHealth] = useState<HwpHealthState | null>(null);
  const poll = useRef<ReturnType<typeof pollHwpHealth> | null>(null);
  const status = health?.status;
  useEffect(() => {
    poll.current = pollHwpHealth(setHealth);
    return () => {poll.current?.stop();};
  }, []);
  return <div role="status" aria-label="HWP Worker 상태" className="border-y py-3 text-sm break-words">
    <strong>HWP Worker · {status ? states[status.code] || "상태 확인 필요" : "확인 중"}</strong>
    <button className="ml-3 underline" onClick={() => poll.current?.refresh()}>상태 다시 확인</button>
    {health?.checkedAt ? <p>마지막 확인: {new Date(health.checkedAt).toLocaleTimeString("ko-KR")}</p> : null}
    {health?.stale && <p className="text-amber-800">현재 조회 실패 · {health.checkedAt ? "이전 상태입니다. " : ""}{health.error === "worker_timeout" ? "응답 지연" : health.error === "worker_offline" ? "Worker 연결 실패" : "상태 확인 필요"}</p>}
    {status?.code === "worker_connected" && <p>{status.generation_verified ? "실파일 생성 검증됨" : "연결 확인 · 실파일 생성 검증은 별도"}</p>}
    {status?.operation?.stage && <p>{stages[status.operation.stage] || "한글 처리"} · {Math.round(status.operation.elapsed_seconds || 0)}초</p>}
    {status?.operation?.failure_stage && <p>최초 실패: {stages[status.operation.failure_stage] || status.operation.failure_stage}</p>}
    {status?.operation?.operation_id && <p className="text-xs">작업번호: {status.operation.operation_id}</p>}
    {status?.code === "worker_recovery" && <p>기존 파일과 한글 작업의 종료를 확인한 뒤 복구하세요. 추가 실행은 차단됩니다.</p>}
  </div>;
}
