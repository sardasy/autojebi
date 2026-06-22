import { expect, test } from "@playwright/test";

import {
  API_BASE,
  apiHeaders,
  cleanupE2ENotices,
  loadFixture,
  seedAnalyzedNotice,
  uniqueE2EId,
} from "./helpers";

const baseFixture = loadFixture("real-g2b-notice.json");

test.describe("program search and save workflow", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupE2ENotices(request);
  });

  test("saved G2B fixture appears in list and duplicate upsert preserves analyzed state", async ({
    page,
    request,
  }) => {
    const noticeNo = uniqueE2EId("SAVE");
    const title = `${baseFixture.title} ${noticeNo}`;
    const fixture = await seedAnalyzedNotice(request, baseFixture, {
      notice_no: noticeNo,
      title,
    });

    const duplicate = await request.post(`${API_BASE}/notices/upsert`, {
      headers: apiHeaders(),
      data: {
        notice_no: fixture.notice_no,
        title: `${title} duplicate-write`,
        source: fixture.source,
        raw: fixture.raw,
      },
    });
    expect(duplicate.ok()).toBeTruthy();
    const duplicateBody = await duplicate.json();
    expect(duplicateBody.status).toBe("analyzed");
    expect(duplicateBody.analysis).toBeTruthy();

    await page.goto(`/notices?mode=saved&lifecycle=all&q=${encodeURIComponent(noticeNo)}&page_size=50`);
    await expect(page.getByRole("heading", { name: "저장 공고 업무 큐" })).toBeVisible();
    await expect(page.getByRole("link", { name: /강원본부 휴대용 변압기 시험기/ })).toBeVisible();
    await expect(page.getByText("G2B").first()).toBeVisible();
    await expect(page.getByText("분석").first()).toBeVisible();

    await page.getByRole("link", { name: /강원본부 휴대용 변압기 시험기/ }).first().click();
    await expect(page.getByRole("heading", { name: /강원본부 휴대용 변압기 시험기/ })).toBeVisible();
    await expect(page.getByText("한국전력공사 강원지역본부").first()).toBeVisible();
    await expect(page.getByText("54,545,455원")).toBeVisible();
  });
});
