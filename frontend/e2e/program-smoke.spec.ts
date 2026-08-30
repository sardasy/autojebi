import { expect, test } from "@playwright/test";

import { API_BASE, API_KEY, apiHeaders } from "./helpers";

test.describe("program smoke", () => {
  test("home, notices, admin, and health endpoints are reachable", async ({
    page,
    request,
  }) => {
    const health = await request.get(`${API_BASE}/healthz`, {
      headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
    });
    expect(health.ok(), `healthz failed: ${health.status()}`).toBeTruthy();

    await page.goto("/");
    await expect(page).toHaveURL(/\/search$/);

    await page.goto("/notices?mode=g2b");
    await expect(page.getByRole("heading", { name: "G2B 실시간 공고 검색" })).toBeVisible();
    await expect(page.getByText(/검색어를 입력하면 나라장터 OpenAPI/)).toBeVisible();

    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "어드민" })).toBeVisible();
    await expect(page.getByText("공고 수동 Upsert")).toBeVisible();
    await expect(page.getByText("KJEBI 메일 추출")).toBeVisible();
    await expect(page.getByText("SKU 카탈로그 인제스트")).toBeVisible();
  });

  test("search API validation still guards bad live-search input", async ({ request }) => {
    const response = await request.post(`${API_BASE}/notices/search`, {
      headers: apiHeaders(),
      data: { keyword: "", page: 1, page_size: 50 },
    });
    expect(response.status()).toBe(422);
  });
});
