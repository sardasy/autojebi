import { expect, test } from "@playwright/test";

import {
  cleanupE2ENotices,
  loadFixture,
  markRequiredChecklistReady,
  postApi,
  uniqueE2EId,
  upsertNotice,
} from "./helpers";

const baseFixture = loadFixture("real-g2b-notice.json");

test.describe("program spec items and HWP workflow", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupE2ENotices(request);
  });

  test("extracts spec items, saves a reviewed value, runs HWP compose, and shows export state", async ({
    page,
    request,
  }) => {
    const noticeNo = uniqueE2EId("HWP");
    const title = `${baseFixture.title} ${noticeNo}`;
    await upsertNotice(request, baseFixture, { notice_no: noticeNo, title });

    await page.goto(`/notices?mode=saved&lifecycle=all&q=${encodeURIComponent(noticeNo)}&page_size=50`);
    await page.getByRole("link", { name: /강원본부 휴대용 변압기 시험기/ }).first().click();

    await page.getByRole("button", { name: "분석", exact: true }).click();
    await expect(page.getByText(/분석 완료|분석 실패/)).toBeVisible({ timeout: 90_000 });
    await page.reload();

    const initialWorkflowRail = page.locator("section", { hasText: "입찰 업무 흐름" }).first();
    await initialWorkflowRail.getByRole("link", { name: "서류 준비로 이동" }).click();
    await expect(page).toHaveURL(/#documents$/);
    await expect(page.locator("#documents")).toBeVisible();

    const docAnalyzeButton = page.getByRole("button", { name: "서류 분석" });
    if (await docAnalyzeButton.isEnabled()) {
      await docAnalyzeButton.click();
      await expect(page.getByText(/서류 분석 완료|서류 분석 실패/)).toBeVisible({ timeout: 90_000 });
      await page.reload();
    }

    await markRequiredChecklistReady(request, noticeNo, ["technical_compliance"]);

    const workflowRail = page.locator("section", { hasText: "입찰 업무 흐름" }).first();
    await workflowRail.getByRole("link", { name: "규격 항목으로 이동" }).click();
    await expect(page).toHaveURL(/#spec-items$/);
    await expect(page.locator("#spec-items")).toBeVisible();

    await page.getByRole("button", { name: "규격 추출" }).click();
    await expect(page.getByText(/규격 추출 완료/)).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("규격 항목").first()).toBeVisible();

    const voltageRow = page.locator("tbody tr", { hasText: "정격전압" }).first();
    await expect(voltageRow).toBeVisible();
    const voltageInput = voltageRow.locator("input");
    await voltageInput.fill("22.9kV 대응 가능");
    await voltageInput.blur();
    await expect(page.getByText(/정격전압 저장/)).toBeVisible();
    await voltageRow.locator("select").selectOption("matched");
    await expect(page.getByText(/정격전압 저장/)).toBeVisible();

    const compose = await postApi(
      request,
      `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-compose`,
      {
        include_bid_form: false,
        include_technical_compliance: true,
      },
    );
    expect([200, 502]).toContain(compose.status());
    await page.reload();

    await expect(page.getByText("규격대응표 내보내기")).toBeVisible();
    await page.getByRole("button", { name: "Excel 생성" }).click();
    await expect(page.getByText(/Excel 파일 생성 완료|Excel 생성 실패/)).toBeVisible();
    await page.reload();
    await expect(page.getByRole("link", { name: "다운로드" }).first()).toBeVisible();

    await page.getByRole("button", { name: "제안서 HWP 작성" }).click();
    const proposalModal = page.getByRole("dialog", { name: "제안서 HWP 작성" });
    await expect(proposalModal.getByText(/HWP agent:/)).toBeVisible();
    await expect(proposalModal.getByText(/규격 항목:/)).toBeVisible();
    await expect(proposalModal.getByText("생성 섹션")).toBeVisible();
    await expect(proposalModal.getByText("규격 대응 요약")).toBeVisible();
    await expect(proposalModal.getByText("규격 대응 샘플")).toBeVisible();
    await expect(proposalModal.getByText(/정격전압: 22.9kV 대응 가능/)).toBeVisible();
    await proposalModal.getByRole("button", { name: "작성", exact: true }).click();
    await expect(
      page.getByText(
        /제안서 HWP 생성 완료|제안서 HWP 생성 실패|제안서 초안이 저장되었습니다|제안서 작성 실패/,
      ),
    ).toBeVisible();
    if (await proposalModal.isVisible()) {
      await page.keyboard.press("Escape");
      await expect(proposalModal).toBeHidden();
    }
    await expect(page.getByText("제안서 HWP 초안")).toBeVisible();
    await expect(page.getByText("제안서 섹션")).toBeVisible();
    await expect(page.getByText("공고 개요").last()).toBeVisible();
    await expect(page.getByText("규격 대응표").last()).toBeVisible();
    await expect(page.getByText("22.9kV 대응 가능").last()).toBeVisible();
    const finalWorkflowRail = page.locator("section", { hasText: "입찰 업무 흐름" }).first();
    const proposalStep = finalWorkflowRail.locator("li", { hasText: "제안서 초안" });
    await expect(proposalStep.getByText("완료")).toBeVisible();
    await expect(proposalStep.getByText("초안/파일 생성됨")).toBeVisible();
    await finalWorkflowRail.getByRole("link", { name: "제안서 작성으로 이동" }).click();
    await expect(page).toHaveURL(/#spec-items$/);
  });
});
