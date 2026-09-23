import {expect, test} from "@playwright/test";

test("manual extraction comparison keeps source review unchanged", async ({page}) => {
  const mutations: string[] = [];
  let compared = false;
  const candidate = {text: "비교 결과 220 V", page_mode: "section", warnings: [],
    tables: [{locator: "blocks/0", rows: 1, cols: 1}], fragments: [{locator: "blocks/0/cells/0/0", kind: "table_cell", text: "220 V", row: 0, col: 0, row_span: 1, col_span: 1}]};
  const job = {id: "comparison", kind: "document_compare", input_version: 2, status: "succeeded", quality: "warning", error: null,
    created_at: "2026-09-23T00:00:00Z", result: {engine_version: "4.14.1", comparisons: [{document_id: "src", input_version: 2,
      name: "합성.hwpx", status: "compared", baseline_text: "기존 본문 200 V", candidate,
      comparison: {state: "different", missing_token_count: 1, added_token_count: 1}}]}};
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") mutations.push(path);
    if (path.endsWith("/workspace-session")) return route.fulfill({json: {enabled: false, actor: null}});
    if (path.endsWith("/workspace")) return route.fulfill({json: {
      notice_no: "E2E-KORDOC", version: 2, decision: "pending", ready: false, source_changed: false, kordoc_comparison_enabled: true,
      inputs: {notice: {title: "추출 비교 합성 검증", org_name: null, close_date: null}, company: {},
        documents: [{id: "src", name: "합성.hwpx", role: "notice_source", text: "", confirmed: false}], requirements: [], checklist: []},
      source_attachments: [], blockers: [], next_action: "원문 대조", reviews: [], jobs: compared ? [job] : [],
    }});
    if (path.endsWith("/jobs")) {
      expect(route.request().postDataJSON()).toMatchObject({kind: "document_compare", input_version: 2});
      compared = true;
      return route.fulfill({json: job});
    }
    return route.fulfill({json: {items: [], available: false, state: "unknown", required_missing: [], mapping_fields: []}});
  });
  await page.goto("/workspace/E2E-KORDOC");
  await page.getByRole("tab", {name: "2. 공고 서류 검토"}).click();
  await page.getByText("문서 추출 비교 · 검증용", {exact: true}).click();
  expect(mutations).toEqual([]);
  await page.getByRole("button", {name: "문서 추출 비교 실행"}).click();
  await expect(page.getByText("비교 결과 220 V", {exact: true})).toBeVisible();
  await expect(page.getByText(/실제 페이지 번호 미확인/)).toBeVisible();
  await page.getByText("표·셀 위치 후보 확인", {exact: true}).click();
  await expect(page.getByText("blocks/0/cells/0/0", {exact: true})).toBeVisible();
  expect(mutations).toEqual(["/api/v2/notices/E2E-KORDOC/jobs"]);
  await page.screenshot({path: "test-results/document-comparison.png", fullPage: true});
});
