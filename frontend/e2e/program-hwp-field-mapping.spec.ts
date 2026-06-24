import { expect, test } from "@playwright/test";

import {
  API_BASE,
  apiHeaders,
  cleanupE2ENotices,
  loadFixture,
  postApi,
  seedDocumentAutomation,
  uniqueE2EId,
} from "./helpers";

// M14 HWP 필드매핑 경로 전용 커버리지.
// 기존 spec(program-spec-hwp, real-notice-document-flow)은 hwp-compose/proposal-compose만
// 실행하고, 필드매핑 경로(hwp-templates / hwp-context / hwp-put-fields / hwp-jobs review)는
// 비어 있었다. 이 경로는 `python -m api.hwp_fields seed`로 hwp_templates +
// document_field_mappings + company_profiles[default]가 적재돼 있어야 동작한다.
//
// UI 모달은 규격 저장 직후 revalidation과 경합해 불안정하므로(program-spec-hwp의 주석 참고)
// 엔드포인트를 직접 호출해 안정적으로 검증한다. HWP 에이전트 부재/실패 시 502/409를 허용하되,
// 200이면 job/replaced/export까지 추가 단언한다.

const ALLOWED_TRANSFORMS = new Set([
  "none",
  "date_yyyy_mm_dd",
  "number_comma",
  "business_number_dash",
  "strip",
  "truncate_1000",
]);

const baseFixture = loadFixture("real-g2b-notice.json");

test.describe("program HWP field mapping workflow", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupE2ENotices(request);
  });

  test.afterAll(async ({ request }) => {
    await cleanupE2ENotices(request);
  });

  test("exposes seeded HWP templates with valid field mappings", async ({ request }) => {
    const response = await request.get(`${API_BASE}/documents/hwp-templates`, {
      headers: apiHeaders(false),
    });
    expect(
      response.ok(),
      `hwp-templates failed: ${response.status()} ${await response.text()}`,
    ).toBeTruthy();
    const body = await response.json();
    const items: any[] = body.items ?? [];
    const byKey = new Map<string, any>(items.map((t) => [t.template_key, t]));

    // 시드되지 않은 환경이면 명확히 실패시킨다(필드매핑 경로 전제 조건).
    expect(
      byKey.has("bid_form") && byKey.has("proposal"),
      `expected seeded bid_form/proposal templates, got: ${items.map((t) => t.template_key).join(",")} — run \`python -m api.hwp_fields seed\``,
    ).toBeTruthy();

    const bidForm = byKey.get("bid_form");
    const mappingFields: string[] = (bidForm.mappings ?? []).map((m: any) => m.hwp_field_name);
    for (const field of ["company_name", "notice_no", "title", "org_name"]) {
      expect(mappingFields, `bid_form mapping missing ${field}`).toContain(field);
    }
    for (const template of items) {
      for (const mapping of template.mappings ?? []) {
        expect(
          ALLOWED_TRANSFORMS.has(mapping.transform),
          `unexpected transform ${mapping.transform} on ${template.template_key}.${mapping.hwp_field_name}`,
        ).toBeTruthy();
        expect(typeof mapping.context_path).toBe("string");
        expect(mapping.context_path.length).toBeGreaterThan(0);
      }
    }
  });

  test("previews context and puts fields, then reviews the generated job", async ({ request }) => {
    const noticeNo = uniqueE2EId("FIELDMAP");
    const title = `${baseFixture.title} ${noticeNo}`;
    await seedDocumentAutomation(request, baseFixture, { notice_no: noticeNo, title });
    const encoded = encodeURIComponent(noticeNo);

    // 1) 컨텍스트 미리보기 — bid_form
    const bidContext = await postApi(request, `/notices/${encoded}/documents/hwp-context`, {
      template_key: "bid_form",
    });
    expect(
      bidContext.ok(),
      `bid_form hwp-context failed: ${bidContext.status()} ${await bidContext.text()}`,
    ).toBeTruthy();
    const bidContextBody = await bidContext.json();
    expect(bidContextBody.notice_no).toBe(noticeNo);
    expect(bidContextBody.template.template_key).toBe("bid_form");
    // notice 매핑은 시드/공고에서 채워져야 한다.
    expect(bidContextBody.input_values.notice_no).toBe(noticeNo);
    expect(typeof bidContextBody.input_values.title).toBe("string");
    expect(Array.isArray(bidContextBody.required_missing)).toBeTruthy();

    // 2) 컨텍스트 미리보기 — proposal (proposal payload 빌드 경로)
    const proposalContext = await postApi(request, `/notices/${encoded}/documents/hwp-context`, {
      template_key: "proposal",
    });
    expect(
      proposalContext.ok(),
      `proposal hwp-context failed: ${proposalContext.status()} ${await proposalContext.text()}`,
    ).toBeTruthy();
    const proposalContextBody = await proposalContext.json();
    expect(proposalContextBody.template.template_key).toBe("proposal");
    expect(Array.isArray(proposalContextBody.required_missing)).toBeTruthy();

    // 3) 필드 주입 — bid_form.
    //    실제 계약: API는 에이전트 실패 시에도 HTTP 200을 반환하고 실패를 job.status에 담는다
    //    (예: 에이전트에 /document/put-fields 미구현 시 job.status="failed" + error_detail).
    //    드물게 라우터 단에서 502/409가 날 수 있어 허용한다.
    const putFields = await postApi(request, `/notices/${encoded}/documents/hwp-put-fields`, {
      template_key: "bid_form",
      visible: false,
    });
    expect([200, 502, 409]).toContain(putFields.status());

    if (putFields.status() === 200) {
      const putBody = await putFields.json();
      expect(putBody.notice_no).toBe(noticeNo);
      const job = putBody.job;
      expect(typeof job?.id).toBe("number");
      expect(typeof job?.status).toBe("string");
      if (job.status === "completed") {
        // 에이전트가 200을 주면 autojebi는 항상 export를 기록한다. replaced 건수는
        // 템플릿 작성에 의존한다 — 템플릿에 hwp_field_name과 같은 누름틀이 있으면 >0,
        // {{placeholder}} 방식이면 0이고 export는 validation_status="warning"으로 기록된다.
        // 따라서 export 존재만 단언하고 replaced>0은 강제하지 않는다.
        expect(putBody.export, "completed job must record an export").not.toBeNull();
        expect(Array.isArray(job.replaced)).toBeTruthy();
      } else {
        // 실패 job은 진단 가능한 error_detail을 남겨야 한다(조용한 실패 금지).
        expect(job.error_detail, "failed job must carry error_detail").toBeTruthy();
      }

      // 4) job 리뷰 승인 — job 상태(완료/실패)와 무관하게 리뷰 워크플로는 동작해야 한다.
      const review = await postApi(
        request,
        `/notices/${encoded}/documents/hwp-jobs/${job.id}/review`,
        { review_status: "approved", reviewed_by: "e2e" },
      );
      expect(
        review.ok(),
        `hwp-job review failed: ${review.status()} ${await review.text()}`,
      ).toBeTruthy();
      const reviewBody = await review.json();
      expect(reviewBody.job.review_status).toBe("approved");
      expect(reviewBody.job.reviewed_by).toBe("e2e");
    }

    // 5) 없는 job_id 리뷰 → 404 (에이전트 상태와 무관하게 항상 검증)
    const missingReview = await postApi(
      request,
      `/notices/${encoded}/documents/hwp-jobs/99999999/review`,
      { review_status: "approved" },
    );
    expect(missingReview.status()).toBe(404);
  });
});
