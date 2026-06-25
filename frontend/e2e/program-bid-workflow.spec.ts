import { expect, test } from "@playwright/test";

import {
  API_BASE,
  BUSINESS_PDF_PATH,
  apiHeaders,
  cleanupE2ENotices,
  loadFixture,
  postApi,
  uniqueE2EId,
  upsertNotice,
} from "./helpers";

const baseFixture = loadFixture("real-g2b-notice.json");

test.describe("program bid workflow", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupE2ENotices(request);
  });

  test("analyze, grade, documents, common uploads, validation, and dry-run notify", async ({
    page,
    request,
  }) => {
    const noticeNo = uniqueE2EId("BID");
    const title = `${baseFixture.title} ${noticeNo}`;
    await upsertNotice(request, baseFixture, { notice_no: noticeNo, title });

    await page.goto(`/notices?mode=saved&lifecycle=all&q=${encodeURIComponent(noticeNo)}&page_size=50`);
    await page.getByRole("link", { name: /강원본부 휴대용 변압기 시험기/ }).first().click();

    await page.getByRole("button", { name: "분석", exact: true }).click();
    await expect(page.getByText(/분석 완료|분석 실패/)).toBeVisible({ timeout: 90_000 });
    await page.reload();

    const gradeButton = page.getByRole("button", { name: "그레이드", exact: true });
    await expect(gradeButton).toBeEnabled();
    await gradeButton.click();
    const gradeDialog = page.getByRole("dialog", { name: "그레이드 실행" });
    await gradeDialog.getByLabel("Slack 알림 (임계치 초과 시)").uncheck();
    await gradeDialog.getByRole("button", { name: "실행", exact: true }).click();
    await expect(page.getByText(/그레이드 완료|그레이드 실패/)).toBeVisible({ timeout: 90_000 });
    await page.reload();

    await page.getByRole("button", { name: "첨부 서류 가져오기" }).click();
    await expect(page.getByText(/첨부 서류 가져오기 완료/)).toBeVisible({ timeout: 90_000 });
    await page.reload();
    await expect(page.getByText("G2B 첨부").first()).toBeVisible();

    const docAnalyzeButton = page.getByRole("button", { name: "서류 분석" });
    if (await docAnalyzeButton.isEnabled()) {
      await docAnalyzeButton.click();
      await expect(page.getByText(/서류 분석 완료|서류 분석 실패/)).toBeVisible({ timeout: 90_000 });
      await page.reload();
    }

    await expect(page.getByText("입찰참가신청서").first()).toBeVisible();
    await expect(page.getByText("규격대응표 초안")).toBeVisible();

    await page.getByRole("button", { name: "파일 업로드" }).click();
    const uploadModal = page.getByRole("dialog", { name: "서류 파일 업로드" });
    await uploadModal.locator('input[type="file"]').setInputFiles(BUSINESS_PDF_PATH);
    await uploadModal.getByRole("combobox").selectOption("business_registration");
    await uploadModal.getByRole("button", { name: "업로드" }).click();
    await expect(page.getByText(/업로드 완료/)).toBeVisible();
    await page.reload();
    await expect(page.getByRole("link", { name: "business-registration-sample.pdf" }).first()).toBeVisible();

    await page.getByRole("button", { name: "공통 서류 가져오기" }).click();
    const commonModal = page.getByRole("dialog", { name: "공통 서류 가져오기" });
    await commonModal.locator('input[type="file"]').setInputFiles(BUSINESS_PDF_PATH);
    await commonModal.getByRole("combobox").selectOption("business_registration");
    const registerCommonButton = commonModal.getByRole("button", { name: "등록" });
    await expect(registerCommonButton).toBeVisible();
    await registerCommonButton.dispatchEvent("click");
    await expect(page.getByText(/공통 서류 등록/)).toBeVisible();
    const importCommonButton = commonModal
      .locator("tbody tr", { hasText: "business-registration-sample.pdf" })
      .first()
      .getByRole("button", { name: "가져오기" });
    await expect(importCommonButton).toBeEnabled();
    await importCommonButton.dispatchEvent("click");
    await expect(page.getByText(/가져오기 완료/)).toBeVisible();
    await page.reload();
    await expect(page.getByText("공통 서류함").first()).toBeVisible();

    await page.getByRole("button", { name: "제출 전 검증" }).click();
    await expect(page.getByText(/제출 전 검증 통과|필수 누락/)).toBeVisible();

    const notify = await postApi(request, `/notices/${encodeURIComponent(noticeNo)}/notify`, {
      dry_run: true,
    });
    expect(
      notify.ok(),
      `notify dry-run failed: ${notify.status()} ${await notify.text()}`,
    ).toBeTruthy();
    const notified = await request.get(`${API_BASE}/notices/${encodeURIComponent(noticeNo)}`, {
      headers: apiHeaders(false),
    });
    expect(notified.ok()).toBeTruthy();
    expect(["notified", "digest_queued", "archived_low"]).toContain((await notified.json()).status);
  });
});
