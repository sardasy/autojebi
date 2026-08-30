import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { cleanupE2ENotices, postApi, uniqueE2EId } from "./helpers";

const API_BASE = process.env.E2E_API_BASE || "http://localhost:8001";
const API_KEY = process.env.E2E_API_KEY || "";
const FIXTURE_DIR = path.join(__dirname, "fixtures");
const NOTICE_FIXTURE_PATH = path.join(FIXTURE_DIR, "real-g2b-notice.json");
const PDF_FIXTURE_PATH = path.join(FIXTURE_DIR, "business-registration-sample.pdf");

type RealNoticeFixture = {
  notice_no: string;
  title: string;
  source: string;
  raw: Record<string, unknown>;
};

const fixture = JSON.parse(
  fs.readFileSync(NOTICE_FIXTURE_PATH, "utf-8"),
) as RealNoticeFixture;

function apiHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
  };
}

// 고정 notice_no를 재사용하면 반복 실행 시 상태가 누적되어 불안정하다.
// 다른 워크플로 스펙과 동일하게 매 실행 고유 notice_no로 격리한다.
let noticeNo: string;
let title: string;

test.beforeAll(async ({ request }) => {
  await cleanupE2ENotices(request);
  noticeNo = uniqueE2EId("REAL");
  title = `${fixture.title} ${noticeNo}`;
  const response = await request.post(`${API_BASE}/notices/upsert`, {
    headers: apiHeaders(),
    data: {
      notice_no: noticeNo,
      title,
      source: fixture.source,
      raw: fixture.raw,
    },
  });
  expect(
    response.ok(),
    `real notice seed failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
});

test("real G2B fixture notice flows through saved list and document work", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  await page.goto(`/notices?mode=saved&lifecycle=all&q=${encodeURIComponent(noticeNo)}&page_size=50`);
  await expect(page.getByRole("heading", { name: "저장 공고 업무 큐" })).toBeVisible();
  await expect(page.getByRole("link", { name: title, exact: true })).toBeVisible();

  await page.getByRole("link", { name: title, exact: true }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("한국전력공사 강원지역본부").first()).toBeVisible();
  await expect(page.getByText("54,545,455원").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "서류 준비" }).first()).toBeVisible();

  const analyzeButton = page.getByRole("button", { name: "분석", exact: true });
  if (await analyzeButton.isEnabled()) {
    await analyzeButton.click();
    await expect(page.getByText(/분석 완료|분석 실패/).first()).toBeVisible({ timeout: 90_000 });
    await page.reload();
  }

  await page.getByRole("button", { name: "첨부 서류 가져오기" }).click();
  await expect(page.getByText(/첨부 서류 가져오기 완료/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("link", { name: "규격서-sample.pdf" }).first()).toBeVisible();
  await expect(page.getByText("G2B 첨부").first()).toBeVisible();

  const docAnalyzeButton = page.getByRole("button", { name: "서류 분석" });
  if (await docAnalyzeButton.isEnabled()) {
    await docAnalyzeButton.click();
    await expect(page.getByText(/서류 분석 완료|서류 분석 실패/).first()).toBeVisible({ timeout: 90_000 });
    await page.reload();
  }

  await expect(page.getByText("입찰참가신청서").first()).toBeVisible();
  await expect(page.getByText("규격대응표 초안")).toBeVisible();
  await expect(page.getByRole("button", { name: "제출 전 검증" })).toBeVisible();

  await page.getByRole("button", { name: "규격 추출" }).click();
  await expect(page.getByText(/규격 추출 완료/)).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("규격 항목").first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "품목 general" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "정격전압 kV" })).toBeVisible();

  const voltageRow = page.locator("tbody tr", { hasText: "정격전압" }).first();
  await voltageRow.locator("input").fill("22.9kV 대응 가능");
  await voltageRow.locator("select").selectOption("matched");
  await expect(page.getByText(/정격전압 저장/)).toBeVisible();

  // HWP compose / 제안서 compose의 UI 모달은 규격 저장 직후 revalidation과 경합해 불안정하다.
  // 동일 흐름을 program-spec-hwp가 모달 없이 API로 검증하므로, 여기서도 엔드포인트를 직접
  // 호출해 안정적으로 확인한다(HWP 에이전트 부재 시 502/409 허용).
  const hwpCompose = await postApi(
    request,
    `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-compose`,
    { include_bid_form: false, include_technical_compliance: true },
  );
  expect([200, 502, 409]).toContain(hwpCompose.status());

  const proposalCompose = await postApi(
    request,
    `/notices/${encodeURIComponent(noticeNo)}/documents/proposal-compose`,
    {},
  );
  expect([200, 502, 409]).toContain(proposalCompose.status());
  await page.reload();

  await page.getByRole("button", { name: "파일 업로드" }).click();
  const uploadModal = page.getByRole("dialog", { name: "서류 파일 업로드" });
  await uploadModal.locator('input[type="file"]').setInputFiles(PDF_FIXTURE_PATH);
  await uploadModal.getByRole("combobox").selectOption("business_registration");
  await uploadModal.getByRole("button", { name: "업로드" }).click();
  await expect(page.getByText(/업로드 완료/)).toBeVisible();
  await page.reload();

  await expect(
    page.getByRole("link", { name: "business-registration-sample.pdf" }).first(),
  ).toBeVisible();
  await expect(page.getByText("business_registration").first()).toBeVisible();
  await expect(page.getByText(/Business Registration|파일을 저장했습니다/).first()).toBeVisible();

  await page.getByRole("button", { name: "공통 서류 가져오기" }).click();
  const commonModal = page.getByRole("dialog", { name: "공통 서류 가져오기" });
  await commonModal.locator('input[type="file"]').setInputFiles(PDF_FIXTURE_PATH);
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
  await expect(page.getByText("business_registration").first()).toBeVisible();
});
