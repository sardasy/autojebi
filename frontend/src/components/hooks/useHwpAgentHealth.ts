"use client";

import { useEffect, useState } from "react";

import { actionGetHwpAgentHealth } from "@/lib/actions";

export type HwpAgentStatus = "checking" | "ok" | "unavailable";

/**
 * 다이얼로그가 열릴 때(open=true) milim-hwp-agent 헬스를 1회 조회한다.
 * 언마운트/재오픈 경합은 alive 플래그로 무시.
 */
export function useHwpAgentHealth(open: boolean): HwpAgentStatus {
  const [agentStatus, setAgentStatus] = useState<HwpAgentStatus>("checking");

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setAgentStatus("checking");
    actionGetHwpAgentHealth()
      .then((result) => {
        if (alive) setAgentStatus(result.ok ? "ok" : "unavailable");
      })
      .catch(() => {
        if (alive) setAgentStatus("unavailable");
      });
    return () => {
      alive = false;
    };
  }, [open]);

  return agentStatus;
}
