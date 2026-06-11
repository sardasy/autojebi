import { expect, test } from "@playwright/test";

/**
 * Playwright e2e — M14 Stage 1 온톨로지 읽기 API.
 *
 * 전제:
 *   - docker compose 가동 (autojebi-api healthy)
 *   - `python -m api.ontology seed` 1회 실행됨 (운영 DB에 통제어휘 적재)
 */

const API_BASE = process.env.E2E_API_BASE || "http://localhost:8001";
const API_KEY = process.env.E2E_API_KEY || "";

function authHeaders(): Record<string, string> | undefined {
  return API_KEY ? { "X-API-Key": API_KEY } : undefined;
}

test("GET /ontology/concepts?kind=role → 4건 (시드된 역할)", async ({ request }) => {
  const r = await request.get(`${API_BASE}/ontology/concepts?kind=role`, {
    headers: authHeaders(),
  });
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.total).toBe(4);
  expect(body.items).toHaveLength(4);
  for (const it of body.items) {
    expect(it.kind).toBe("role");
    expect(it.canonical_key).toMatch(/^role:/);
  }
});

test("GET /ontology/concepts/product_category:hil → 200, display_name_ko=HIL", async ({
  request,
}) => {
  const r = await request.get(
    `${API_BASE}/ontology/concepts/product_category:hil`,
    { headers: authHeaders() },
  );
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.canonical_key).toBe("product_category:hil");
  expect(body.display_name_ko).toBe("HIL");
  expect(body.kind).toBe("product_category");
});

test("GET /ontology/concepts/missing:foo → 404", async ({ request }) => {
  const r = await request.get(`${API_BASE}/ontology/concepts/missing:foo`, {
    headers: authHeaders(),
  });
  expect(r.status()).toBe(404);
});

test("GET /ontology/aliases?concept_id=999999 → 200 + []", async ({ request }) => {
  const r = await request.get(
    `${API_BASE}/ontology/aliases?concept_id=999999`,
    { headers: authHeaders() },
  );
  expect(r.status()).toBe(200);
  expect(await r.json()).toEqual([]);
});

test("GET /ontology/aliases → 422 (concept_id 필수)", async ({ request }) => {
  const r = await request.get(`${API_BASE}/ontology/aliases`, {
    headers: authHeaders(),
  });
  expect(r.status()).toBe(422);
});
