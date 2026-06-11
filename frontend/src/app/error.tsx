"use client";

import { useEffect } from "react";

/**
 * Next.js 글로벌 에러 경계 — 서버/클라이언트 양쪽에서 잡히지 않은 예외를 사용자에게 표시.
 * Next.js 컨벤션 (`app/error.tsx`): 자동 발동.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 운영 환경에서는 외부 로깅 도구로 전송 (현재는 콘솔만)
    // eslint-disable-next-line no-console
    console.error("GlobalError:", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="max-w-md rounded border border-red-700 bg-red-950/40 p-6 space-y-3 text-center">
        <p className="text-lg font-semibold text-red-300">예기치 못한 오류</p>
        <p className="text-sm text-slate-300">
          페이지를 표시하던 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.
        </p>
        {error.digest ? (
          <p className="text-xs font-mono text-slate-500">
            error-id: {error.digest}
          </p>
        ) : null}
        <button
          type="button"
          onClick={reset}
          className="rounded bg-brand-500 hover:bg-brand-600 px-4 py-1.5 text-sm font-medium text-white"
        >
          다시 시도
        </button>
      </div>
    </div>
  );
}
