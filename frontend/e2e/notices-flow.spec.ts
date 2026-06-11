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
  await expect(page.getByRole("heading", { name: "공고 목록" })).toBeVisible();
  // KJEBI 카피
  await expect(page.getByText("검색 필터", { exact: true })).toBeVisible();
  await expect(page.getByText(/간편검색/)).toBeVisible();
  await expect(page.getByText("게시일시", { exact: true })).toBeVisible();
  await expect(page.getByText("입찰 마감일시", { exact: true })).toBeVisible();
  await expect(page.getByText(/입찰 마감 제외/)).toBeVisible();
  // 빠른 칩
  await expect(page.getByRole("button", { name: "1주일" })).toBeVisible();
  await expect(page.getByRole("button", { name: "1개월" })).toBeVisible();
  // 액션
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
  await expect(page.getByRole("heading", { name: "액션" })).toBeVisible();
  await expect(page.getByRole("button", { name: "분석", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "그레이드", exact: true })).toBeVisible();
});

test("notice list shows 서류 column header", async ({ page }) => {
  await page.goto("/notices");
  await expect(page.getByRole("columnheader", { name: "서류" })).toBeVisible();
});

test("notice detail (when present) does NOT show simplified-out 서류·알림·HWP UI", async ({
  page,
}) => {
  await page.goto("/notices");
  const firstRow = page.locator("tbody tr").first();
  const rowCount = await firstRow.count();
  test.skip(rowCount === 0, "no notices seeded in DB; skipping detail flow");

  await firstRow.locator("a").first().click();
  // 1차 단순화로 숨김 — 다시 노출되면 회귀
  await expect(page.getByRole("heading", { name: "서류 준비" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "서류 분석" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "제출 전 검증" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "알림" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "HWP 양식" })).toHaveCount(0);
});
