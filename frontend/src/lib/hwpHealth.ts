import {workspaceFetch} from "./workspace";

export interface HwpStatus {
  code: string; generation_verified?: boolean;
  operation?: {operation_id?: string; stage?: string; failure_stage?: string; elapsed_seconds?: number};
}
export interface HwpHealthState {status: HwpStatus; checkedAt: number; stale: boolean; error?: string}
const normal = new Set(["worker_connected", "worker_running", "worker_recovery"]);
const configuration = new Set(["worker_auth", "worker_token_missing"]);
const transient = new Set(["worker_timeout", "worker_offline", "worker_invalid_health", "worker_unhealthy"]);

/** One request at a time; the deadline includes body consumption and cancellation on teardown. */
export function pollHwpHealth(onState: (state: HwpHealthState) => void) {
  let stopped = false, running = false, failures = 0;
  let scheduled: ReturnType<typeof setTimeout> | undefined;
  let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  let last: HwpHealthState | undefined;
  const update = async () => {
    if (stopped || running) return;
    clearTimeout(scheduled);
    running = true;
    controller = new AbortController();
    const active = controller;
    let delay = 3000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = deadlineTimer = setTimeout(() => {active.abort(); reject(new Error("worker_timeout"));}, 5000);
      });
      const read = async () => {
        const response = await workspaceFetch("/hwp-worker", {signal: active.signal});
        if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "diagnostic_auth" : "diagnostic_failed");
        const body = await response.json() as HwpStatus;
        if (!body || ![...normal, ...configuration, ...transient].includes(body.code)) throw new Error("worker_invalid_health");
        return body;
      };
      const status = await Promise.race([read(), timeout]);
      if (transient.has(status.code)) throw new Error(status.code);
      failures = 0;
      delay = configuration.has(status.code) ? 30000 : 3000;
      if (!stopped) {last = {status, checkedAt: Date.now(), stale: false}; onState(last);}
    } catch (error) {
      const code = error instanceof Error ? error.message : "diagnostic_failed";
      delay = code === "diagnostic_auth" ? 30000 : Math.min(3000 * 2 ** failures++, 30000);
      if (!stopped) onState(last ? {...last, stale: true, error: code} : {
        status: {code}, checkedAt: 0, stale: true, error: code,
      });
    } finally {
      clearTimeout(timer);
      active.abort();
      running = false;
      if (!stopped) scheduled = setTimeout(() => void update(), delay);
    }
  };
  void update();
  return {refresh: () => void update(), stop: () => {stopped = true; clearTimeout(scheduled); clearTimeout(deadlineTimer); controller?.abort();}};
}
