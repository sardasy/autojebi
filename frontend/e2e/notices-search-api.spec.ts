import { expect, test } from "@playwright/test";

/**
 * Playwright e2e — M13 G2B 라이브 검색 API 검증 가드 (G2B 실호출 없음).
 *
 * 페이지네이션 응답 모델·422 검증 경로만 확인. 실 G2B 응답 동선은 비결정적이라
 * 별도 수동 e2e (data/search_e2e_*.md)로 회수.
 */

const API_BASE = process.env.E2E_API_BASE || "http://localhost:8001";
const API_KEY = process.env.E2E_API_KEY || "";

function postSearch(payload: Record<string, unknown>) {
  return {
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
    },
    data: payload,
  };
}

test("POST /notices/search keyword='' → 422", async ({ request }) => {
  const r = await request.post(
    `${API_BASE}/notices/search`,
    postSearch({ keyword: "" }),
  );
  expect(r.status()).toBe(422);
});

test("POST /notices/search page=0 → 422", async ({ request }) => {
  const r = await request.post(
    `${API_BASE}/notices/search`,
    postSearch({ keyword: "x", page: 0, page_size: 50 }),
  );
  expect(r.status()).toBe(422);
});

test("POST /notices/search page_size=999 → 422 (max 200)", async ({ request }) => {
  const r = await request.post(
    `${API_BASE}/notices/search`,
    postSearch({ keyword: "x", page: 1, page_size: 999 }),
  );
  expect(r.status()).toBe(422);
});
