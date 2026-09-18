import { useCallback, useEffect, useState } from "react";
import { jobNames, jobStates, Workspace, WorkspaceJob, workspaceApi } from "@/lib/workspace";

export type Feedback = "loading" | "success" | "error";

/**
 * Workspace data and actions: load, poll while jobs run, mutate, enqueue jobs and report the
 * tracked job's status (moved out of WorkspaceClient, R6).
 * `onMutated` runs after a successful mutation reload so screen-local drafts can be reset.
 */
export function useWorkspace(prefix: string, {onMutated}: {onMutated?: () => void} = {}) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [feedback, setFeedback] = useState<Feedback>("loading");
  const [busy, setBusy] = useState(false);
  const [trackedJob, setTrackedJob] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {setWs(await workspaceApi<Workspace>(`${prefix}/workspace`)); return true;}
    catch(e) {setStatus((e as Error).message); setFeedback("error"); return false;} finally {setLoading(false);}
  }, [prefix]);
  useEffect(() => {void reload();}, [reload]);
  useEffect(() => {
    if (!ws?.jobs.some(j => j.status === "running" || j.status === "queued")) return;
    const timer = setInterval(() => void reload(), 2000);
    return () => clearInterval(timer);
  }, [ws, reload]);

  async function mutate(path: string, body: unknown, message = "저장 완료") {
    setTrackedJob(null);
    setBusy(true); setStatus("처리 중"); setFeedback("loading");
    try {
      const result = await workspaceApi<Partial<WorkspaceJob> | null>(path, body);
      const jobId = result?.id && result?.kind && result?.status ? result.id : null;
      const refreshed = await reload();
      onMutated?.();
      if (refreshed && jobId) setTrackedJob(jobId);
      else if (refreshed) {setStatus(message); setFeedback("success");}
      else {setStatus("요청은 처리됐지만 최신 조회에 실패했습니다. 최신 상태 버튼으로 확인하세요.");}
    }
    catch(e) {setStatus((e as Error).message); setFeedback("error");} finally {setBusy(false);}
  }

  async function run(kind: string, {template_key, visible}: {template_key: string; visible: boolean}) {
    if (!ws) return;
    setBusy(true); setFeedback("loading"); setStatus("작업 접수 중");
    try {
      const job = await workspaceApi<WorkspaceJob>(`${prefix}/jobs`, {kind, input_version: ws.version, idempotency_key: crypto.randomUUID(), template_key, visible});
      setTrackedJob(job.id); await reload();
    } catch(error) {setFeedback("error"); setStatus((error as Error).message);}
    finally {setBusy(false);}
  }

  useEffect(() => {
    const job = ws?.jobs.find(item => item.id === trackedJob);
    if (!job) return;
    const waiting = ["queued", "running"].includes(job.status);
    setFeedback(waiting ? "loading" : job.status === "succeeded" ? "success" : "error");
    setStatus(`${jobNames[job.kind]} · ${jobStates[job.status]}${job.quality === "warning" ? " · 경고·검토 필요" : ""}${job.error ? ` · ${job.error.message} ${job.error.next_action}` : ""}`);
  }, [ws, trackedJob]);

  return {ws, setWs, loading, status, setStatus, feedback, busy, trackedJob, reload, mutate, run};
}
