import { expect, test } from "@playwright/test";

/**
 * Playwright e2e — M9.
 *
 * 전제: docker compose -f infra/docker-compose.yml up -d 실행 중.
 * baseURL은 E2E_BASE_URL env 또는 기본 http://localhost:3000.
 *
 * 기본 화면은 빈 DB에서도 렌더링되어야 하며, 상세/서류 흐름은 API로
 * E2E 전용 공고를 seed한 뒤 확인한다.
 */

const API_BASE = process.env.E2E_API_BASE || "http://localhost:8001";
const API_KEY = process.env.E2E_API_KEY || "";
const SEEDED_NOTICE_NO = "E2E-DOC-001";

test.beforeAll(async ({ request }) => {
  const response = await request.post(`${API_BASE}/notices/upsert`, {
    headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
    data: {
      notice_no: SEEDED_NOTICE_NO,
      title: "E2E 변압기 구매 공고",
      source: "E2E",
      raw: {
        ntceInsttNm: "E2E 테스트기관",
        bidClseDt: "2026-06-10T10:00:00+09:00",
        presmptPrce: "30000000",
        cntrctCnclsMthdNm: "제한경쟁",
      },
    },
  });
  expect(response.ok(), `seed notice failed: ${response.status()} ${await response.text()}`).toBeTruthy();
});

test("home redirects to /notices", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/notices$/);
});

test("notices list renders header + KJEBI-style filter form", async ({ page }) => {
  await page.goto("/notices");
  await expect(page.getByRole("heading", { name: "저장 공고 업무 큐" })).toBeVisible();
  await expect(page.getByText("저장 공고 업무 큐").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "저장 공고" })).toBeVisible();
  await expect(page.getByRole("link", { name: "G2B 검색" })).toBeVisible();
  await expect(page.locator('input[name="q"]')).toBeVisible();
  await expect(page.locator('select[name="lifecycle"]')).toBeVisible();
  await expect(page.locator('select[name="sort"]')).toBeVisible();
  await expect(page.locator('select[name="page_size"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "검색" })).toBeVisible();
  await expect(page.getByRole("link", { name: "초기화" })).toBeVisible();
});

test("admin page renders Upsert + SKU sections", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "어드민" })).toBeVisible();
  await expect(page.getByText("공고 수동 Upsert")).toBeVisible();
  await expect(page.getByText("SKU 카탈로그 인제스트")).toBeVisible();
});

test("notice detail (when present) shows action bar", async ({ page }) => {
  await page.goto("/notices");
  const firstRow = page.locator("tbody tr").first();
  const rowCount = await firstRow.count();
  test.skip(rowCount === 0, "no notices seeded in DB; skipping detail flow");

  await firstRow.locator("a").first().click();
  await expect(page.getByRole("heading", { name: "작업" })).toBeVisible();
  await expect(page.getByRole("button", { name: "분석", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "그레이드", exact: true })).toBeVisible();
});

test("notice list shows 서류 column header", async ({ page }) => {
  await page.goto("/notices");
  await expect(page.getByRole("columnheader", { name: "서류" })).toBeVisible();
});

test("notice detail (when present) shows document preparation UI", async ({
  page,
}) => {
  await page.goto("/notices");
  const firstRow = page.locator("tbody tr").first();
  const rowCount = await firstRow.count();
  test.skip(rowCount === 0, "no notices seeded in DB; skipping detail flow");

  await firstRow.locator("a").first().click();
  await expect(page.getByRole("heading", { name: "서류 준비" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "서류 분석" })).toBeVisible();
  await expect(page.getByRole("button", { name: "제출 전 검증" })).toBeVisible();
  await expect(page.getByRole("button", { name: "알림" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "HWP 양식" })).toHaveCount(0);
});
