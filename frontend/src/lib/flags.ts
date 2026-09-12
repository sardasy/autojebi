/**
 * 서버 전용 기능 플래그. `WORKSPACE_V2_ENABLED`는 여기서만 읽는다.
 * (page/layout 등에서 process.env를 직접 비교하지 말 것 — 값 해석이 흩어지면 화면마다 동선이 갈린다.)
 */
export function isWorkspaceV2Enabled(): boolean {
  return process.env.WORKSPACE_V2_ENABLED === "true";
}

/** 기본 진입 경로 — v2가 켜져 있으면 /workspace, 아니면 기존 /notices. */
export function homePath(): "/workspace" | "/notices" {
  return isWorkspaceV2Enabled() ? "/workspace" : "/notices";
}
