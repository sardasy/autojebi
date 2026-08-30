import { expect, test } from "@playwright/test";

import { cleanupE2ENotices, expectToast, uniqueE2EId } from "./helpers";

test.describe("program admin workflows", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupE2ENotices(request);
  });

  test("manual upsert, mail paste, and SKU ingest controls surface outcomes", async ({
    page,
  }) => {
    const noticeNo = uniqueE2EId("ADMIN");
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "어드민" })).toBeVisible();

    const upsertSection = page.locator("section", { hasText: "공고 수동 Upsert" });
    await upsertSection.getByLabel("notice_no").fill(noticeNo);
    await upsertSection.getByLabel("title").fill(`E2E 어드민 수동 등록 ${noticeNo}`);
    await upsertSection.getByLabel("source").fill("E2E");
    await upsertSection.getByLabel("raw (JSON)").fill(
      JSON.stringify(
        {
          ntceInsttNm: "E2E 어드민기관",
          bidClseDt: "2026-06-30 18:00:00",
          presmptPrce: "1230000",
        },
        null,
        2,
      ),
    );
    await upsertSection.getByRole("button", { name: "Upsert 실행" }).click();
    await expect(page.getByText(/Upsert 완료|Upsert 실패/)).toBeVisible();

    const mailSection = page.locator("section", { hasText: "KJEBI 메일 추출" });
    await mailSection.getByLabel(/메일 본문/).fill(
      [
        `□ 공고번호 : ${uniqueE2EId("MAIL")}`,
        "□ 공고명 : E2E 메일 추출 변압기 시험기",
        "□ 발주기관 : E2E 메일기관",
        "□ 마감일시 : 2026-06-30 18:00",
        "□ 예가 : 10000000",
      ].join("\n"),
    );
    await mailSection.getByRole("button", { name: "추출 & 등록" }).click();
    // 메일 추출은 Claude tool-use라 지연이 크다.
    await expectToast(page, /등록 완료|notice_no 추출 실패|추출 실패/);

    const skuSection = page.locator("section", { hasText: "SKU 카탈로그 인제스트" });
    await skuSection.getByRole("button", { name: "Qdrant에 인제스트" }).click();
    // 카탈로그 임베딩+Qdrant upsert는 수 초 소요 — 기본 5초 대기로는 불안정했다.
    await expectToast(page, /Qdrant 인제스트 완료|인제스트 실패/);

    const hwpSection = page.locator("section", { hasText: "HWP 필드 매핑" });
    await expect(hwpSection).toBeVisible();
    await expect(
      hwpSection.getByRole("button", { name: /새 템플릿|입찰참가신청서|제안서/ }).first(),
    ).toBeVisible();
  });
});
