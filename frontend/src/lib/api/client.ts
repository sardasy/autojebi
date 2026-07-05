/**
 * autojebi API client (M7 minimal 읽기전용).
 *
 * 모든 fetch는 cache: "no-store" — Server Component에서 매번 신선한 데이터.
 * Server Component 환경에서 NEXT_PUBLIC_API_BASE 또는 INTERNAL_API_BASE 사용.
 */

const PUBLIC_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8001";
// 컨테이너 내부에선 INTERNAL_API_BASE (예: http://api:8000)로 SSR 호출 — 옵션.
export const INTERNAL_API_BASE = process.env.INTERNAL_API_BASE || PUBLIC_API_BASE;

// M9: server-side에서만 읽음 (NEXT_PUBLIC_ 안 함 — 브라우저 노출 0)
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || "";

export function defaultHeaders(includeContentType = false): Record<string, string> {
  const h: Record<string, string> = {};
  if (includeContentType) h["Content-Type"] = "application/json";
  if (INTERNAL_API_KEY) h["X-API-Key"] = INTERNAL_API_KEY;
  return h;
}

export type QsValue = string | number | boolean | string[] | number[] | undefined | null;

function qs(params: Record<string, QsValue>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      for (const item of v) {
        if (item === undefined || item === null || item === "") continue;
        sp.append(k, String(item));
      }
      continue;
    }
    if (typeof v === "boolean") {
      sp.set(k, v ? "true" : "false");
      continue;
    }
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// 테스트에서 qs round-trip 검증을 위해 export
export { qs };

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${INTERNAL_API_BASE}${path}`, {
    method: "POST",
    headers: defaultHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    let detail: string;
    try {
      const j = await r.json();
      detail = j?.detail ? JSON.stringify(j.detail) : r.statusText;
    } catch {
      detail = r.statusText;
    }
    throw new Error(`POST ${path} failed: ${r.status} ${detail}`);
  }
  return r.json();
}

// compose 계열은 409(사전검증 실패: 필수 서류 누락 등)를 "정상적인 결과"로 취급한다.
// throw하면 서버액션 경계에서 Next가 프로덕션 메시지를 마스킹해(digest만 전달) 진짜 사유가
// 사라지므로, 검증 오류를 errors 배열에 담아 반환해 다이얼로그가 그대로 노출하게 한다.
export async function postComposeAllowingValidation<T>(
  path: string,
  body: unknown,
  build409: (errors: { stage?: string; detail?: string }[]) => T,
): Promise<T> {
  const r = await fetch(`${INTERNAL_API_BASE}${path}`, {
    method: "POST",
    headers: defaultHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 409) {
    let parsed: unknown;
    try {
      parsed = await r.json();
    } catch {
      parsed = null;
    }
    const d = (parsed as { detail?: unknown })?.detail ?? parsed;
    const detail = d as { errors?: { stage?: string; detail?: string }[]; message?: string };
    const errors =
      Array.isArray(detail?.errors) && detail.errors.length > 0
        ? detail.errors
        : [{ stage: "pre_compose", detail: detail?.message || "사전검증에 실패했습니다" }];
    return build409(errors);
  }
  if (!r.ok) {
    let detail: string;
    try {
      const j = await r.json();
      detail = j?.detail ? JSON.stringify(j.detail) : r.statusText;
    } catch {
      detail = r.statusText;
    }
    throw new Error(`POST ${path} failed: ${r.status} ${detail}`);
  }
  return r.json();
}

/**
 * 백엔드 다운로드 URL을 그대로 호출해 blob을 받는 서버사이드 헬퍼.
 * X-API-Key 헤더 자동 첨부. Next.js API route (route.ts)에서 사용.
 */
export async function fetchDownloadBlob(path: string): Promise<Response> {
  return fetch(`${INTERNAL_API_BASE}${path}`, {
    headers: defaultHeaders(),
    cache: "no-store",
  });
}
