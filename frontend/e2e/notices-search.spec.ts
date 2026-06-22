import { expect, test } from "@playwright/test";

/**
 * Playwright e2e — 공고 목록 검색 UI.
 *
 * 저장 공고 필터는 검색어/상태/진행 상태/정렬을 노출하고,
 * G2B 검색 모드는 키워드/조회 기간/빠른 기간을 노출한다.
 */

test("URL에 핵심 필터가 보존되고 새로고침 후 복원된다", async ({ page }) => {
  const target =
    "/notices?mode=saved&q=ABB&lifecycle=active&sort=close_date&direction=asc&page_size=10";
  await page.goto(target);

  await expect(page.locator('input[name="q"]')).toHaveValue("ABB");
  await expect(page.locator('select[name="lifecycle"]')).toHaveValue("active");
  await expect(page.locator('select[name="sort"]')).toHaveValue("close_date");
  await expect(page.locator('select[name="direction"]')).toHaveValue("asc");
  await expect(page.locator('select[name="page_size"]')).toHaveValue("10");
});

test("상태 다중 선택이 URL에 직렬화된다", async ({ page }) => {
  await page.goto("/notices?mode=saved");

  await page.locator('label:has(input[name="status"][value="analyzed"])').click();
  await page.locator('label:has(input[name="status"][value="form_filled"])').click();

  await page.getByRole("button", { name: "검색" }).click();
  await expect(page).toHaveURL(/status=analyzed/);
  await expect(page).toHaveURL(/status=form_filled/);
});

test("전체 초기화 링크 → /notices 로 돌아감", async ({ page }) => {
  await page.goto("/notices?mode=saved&q=test&status=analyzed&page_size=10");
  await page.getByRole("link", { name: "초기화" }).first().click();
  await expect(page).toHaveURL(/\/notices\?mode=saved$/);
});

test("페이지네이션 — 총 N건 표시", async ({ page }) => {
  await page.goto("/notices?lifecycle=all&page_size=5");
  const rowsCount = await page.locator("tbody tr").count();
  test.skip(rowsCount === 0, "no notices seeded — pagination not exercised");
  await expect(page.locator("main")).toContainText(/총\s*[\d,]+\s*건/);
});

test("G2B 검색 모드는 기간 필터와 빠른 기간 버튼을 노출한다", async ({ page }) => {
  await page.goto("/notices?mode=g2b&q=변압기&page_size=10");
  await expect(page.getByText("G2B 실시간 검색").first()).toBeVisible();
  await expect(page.locator('input[name="q"]')).toHaveValue("변압기");
  await expect(page.getByLabel("게시일시 기준")).toBeVisible();
  await expect(page.getByLabel("입찰 마감일시 기준")).toBeVisible();
  await expect(page.getByRole("button", { name: "1주일" })).toBeVisible();
  await expect(page.getByRole("button", { name: "1개월" })).toBeVisible();
  await expect(page.locator('select[name="page_size"]')).toHaveValue("10");
});
