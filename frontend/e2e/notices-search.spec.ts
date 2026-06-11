import { expect, test } from "@playwright/test";

/**
 * Playwright e2e — 공고 목록 검색 UI.
 *
 * 기본 KJEBI-style 필터는 간편검색/기간/마감 제외/검색을 노출하고,
 * 상세 조건은 고급 필터를 펼쳐 조작한다.
 */

test("URL에 핵심 필터가 보존되고 새로고침 후 복원된다", async ({ page }) => {
  const target =
    "/notices?q=ABB&category=IGBT&lifecycle=active&sort=close_date&direction=asc&page_size=10";
  await page.goto(target);

  // 통합 검색 input
  await expect(page.locator('input[name="q"]')).toHaveValue("ABB");

  // lifecycle is driven by the "입찰 마감 제외" switch and serialized as a hidden input.
  await expect(page.locator('input[name="lifecycle"]')).toHaveValue("active");

  // sort/direction/page_size live in the advanced filter DOM.
  await expect(page.locator('select[name="sort"]')).toHaveValue("close_date");
  await expect(page.locator('select[name="direction"]')).toHaveValue("asc");
  await expect(page.locator('select[name="page_size"]')).toHaveValue("10");
});

test("카테고리 다중 선택이 URL에 직렬화된다", async ({ page }) => {
  await page.goto("/notices");

  await page.getByRole("button", { name: /고급 필터 펼치기/ }).click();
  await page.locator("#filter-advanced label").filter({ hasText: "IGBT" }).click();
  await expect(
    page.locator('#filter-advanced input[type="hidden"][name="category"][value="IGBT"]'),
  ).toHaveCount(1);

  await page.getByRole("button", { name: "검색" }).click();
  await expect(page).toHaveURL(/category=IGBT/);
});

test("전체 초기화 링크 → /notices 로 돌아감", async ({ page }) => {
  await page.goto("/notices?q=test&category=IGBT&page_size=10");
  await page.getByRole("link", { name: "초기화" }).first().click();
  await expect(page).toHaveURL(/\/notices$/);
});

test("페이지네이션 — 총 N건 표시", async ({ page }) => {
  await page.goto("/notices?lifecycle=all&page_size=5");
  const rowsCount = await page.locator("tbody tr").count();
  test.skip(rowsCount === 0, "no notices seeded — pagination not exercised");
  await expect(page.locator("main")).toContainText(/총\s*[\d,]+\s*건/);
});

test("'고급 필터' 토글로 상세 조건을 펼칠 수 있다", async ({ page }) => {
  await page.goto("/notices");
  await page.getByRole("button", { name: /고급 필터 펼치기/ }).click();
  await expect(page.locator("#filter-advanced")).toBeVisible();
  await expect(
    page.locator("#filter-advanced").getByText("카테고리", { exact: true }),
  ).toBeVisible();
});
