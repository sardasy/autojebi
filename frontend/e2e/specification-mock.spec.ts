import {createHash} from "node:crypto";
import {expect, test, type Locator, type Page} from "@playwright/test";
import type {SpecificationItem, SpecificationPayload} from "../src/components/SpecificationWorkbench";
import type {Workspace} from "../src/lib/workspace";

test.use({serviceWorkers: "block"});

const noticeNo = "SPEC-MOCK";
const prefix = `/api/v2/notices/${noticeNo}`;
const raw = "출력 전압 0.00100 mV, 허용 범위 -0.00001 이상 1000000000000000000.01 미만. 주변 온도 25 °C.";
const sha = createHash("sha256").update(raw).digest("hex");
const payload: SpecificationPayload = {
  target: "전원 장치", property: "출력 전압", kind: "numeric", operator: "range",
  value: "0.00100", lower: "-0.00001", upper: "1000000000000000000.01",
  lower_inclusive: true, upper_inclusive: false, unit: "mV", identifier: "PART-001",
  conditions: "주변 온도 25 °C", mandatory: true, raw, uncertainty: "0.00010",
  source: {document_id: "notice-text", document_sha256: sha, text_sha256: sha,
    start: 0, end: raw.length, quote: raw, locator: "규격서 2쪽 · 전원 장치 행"},
};
type Correction = {version: number; payload: SpecificationPayload; note: string};

async function mockSpecifications(page: Page, baseURL: string | undefined, options: {enabled?: boolean; conflictOnce?: boolean; writing?: boolean} = {}) {
  // Never start/reset a server or allow this suite to call a real API.
  expect(baseURL, "Set E2E_BASE_URL=http://127.0.0.1:3002").toBeTruthy();
  const origin = new URL(baseURL!).origin;
  expect(["http://127.0.0.1:3002", "http://localhost:3002"]).toContain(origin);
  const enabled = options.enabled !== false;
  const ws: Workspace = {
    notice_no: noticeNo, version: 4, decision: "pending", ready: false, source_changed: false,
    inputs: {
      notice: {title: "시험용 전원 장치 사양 검토 공고", org_name: "검증 기관", close_date: null, base_price: null},
      documents: [{id: "notice-text", name: "시험 규격서.txt", role: "notice_source", confirmed: false, text: raw, text_origin: "manual"}],
      requirements: [{id: "req-1", text: raw, document_id: "notice-text", quote: raw, locator: payload.source.locator,
        category: "technical", mandatory: true, proposed_value: "", evidence_id: null, evidence_quote: "", evidence_locator: "",
        review_status: "pending", compliance: "unassessed"}],
      company: {}, checklist: [], proposal_sections: [], source_reviewed: false, legacy_warning: false,
    },
    jobs: [], reviews: [], blockers: ["사양 확인 필요"], next_action: "원문 사양 확인",
  };
  if (options.writing) {
    ws.writing_plan_current = true;
    ws.inputs.writing_plan = {reviewed_at: "2026-09-11", reviewed_version: 4, items: [
      {id: "proposal", title: "정성제안서", document_kind: "qualitative_proposal", action: "write", document_id: "notice-text", quote: raw},
    ]};
    ws.inputs.documents.push(
      {id: "product-evidence", name: "확인된 제품 시험서", role: "product_evidence", confirmed: true, text: "검증 근거: 출력 전압 0.00100 mV", text_origin: "manual"},
      {id: "company-reference", name: "이전 제안서", role: "company_reference", confirmed: false, text: "참고 인용: 이전 제안서의 전원 장치", text_origin: "manual"},
      {id: "unconfirmed", name: "미확인 제품 근거", role: "product_evidence", confirmed: false, text: "미확인 본문", text_origin: "manual"},
      {id: "expired", name: "기간 문제 회사 증빙", role: "company_evidence", confirmed: true, asset_issue: "expired", text: "만료 본문", text_origin: "manual"},
    );
  }
  let item: SpecificationItem & {input_version: number; notice_no: string; updated_at: string} = {
    id: "spec-1", revision: 2, etag: '"spec-r2-v4"', requirement_id: "req-1",
    payload: structuredClone(payload), validation: {status: "needs_review", codes: ["unit_mismatch"]},
    input_version: ws.version, notice_no: noticeNo, updated_at: "2026-09-11T00:00:00Z",
  };
  const calls = {
    lists: 0, singles: 0, workspace: 0,
    puts: [] as {body: Correction; etag: string | undefined}[],
    searches: [] as {query: string; limit: number; requirement_id?: string}[],
    jobs: [] as {kind: string; input_version: number; idempotency_key: string}[],
    drafts: [] as {text: string; references: {document_id: string; quote: string}[]; version: number}[],
    unexpected: [] as string[], pageErrors: [] as string[],
  };
  const listing = () => ({items: enabled ? [item] : [], input_version: ws.version,
    spec_compliance: "미확인", unresolved_spec_count: 1, source_complete: false, enabled});
  page.on("pageerror", error => calls.pageErrors.push(error.message));
  await page.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) {
      calls.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`);
      return route.abort("blockedbyclient");
    }
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const path = url.pathname;
    const method = request.method();
    if (method === "GET" && path === `${prefix}/workspace`) {
      calls.workspace++;
      return route.fulfill({json: ws});
    }
    if (method === "GET" && path === "/api/v2/hwp-templates") return route.fulfill({json: {items: []}});
    if (method === "GET" && path === "/api/v2/worker/health") return route.fulfill({json: {available: true, state: "idle", heartbeat_at: null, last_failure: null}});
    if (method === "GET" && path === "/api/v2/hwp-worker") return route.fulfill({json: {code: "worker_connected"}});
    if (method === "GET" && path === `${prefix}/prerequisites`) return route.fulfill({json: {
      input_version: ws.version, template_key: url.searchParams.get("template_key") || "", checked_at: "2026-09-11T00:00:00Z",
      hwp_request_available: false, required_missing: [], mapping_fields: [], items: [],
    }});
    if (method === "GET" && path === `${prefix}/specifications`) {
      calls.lists++;
      return route.fulfill({json: listing()});
    }
    if (method === "GET" && path === `${prefix}/specifications/spec-1`) {
      calls.singles++;
      return route.fulfill({json: item, headers: {ETag: item.etag}});
    }
    if (method === "PUT" && path === `${prefix}/specifications/spec-1` && enabled) {
      const body: Correction = request.postDataJSON();
      calls.puts.push({body, etag: request.headers()["if-match"]});
      expect(body.payload.source).toEqual(payload.source);
      expect(body.payload.raw).toBe(raw);
      expect(Object.keys(body).sort()).toEqual(["note", "payload", "version"]);
      if (options.conflictOnce && calls.puts.length === 1) {
        ws.version = 5;
        item = {...item, revision: 3, input_version: 5, etag: '"spec-r3-v5"', payload: {...item.payload, value: "999.000"}};
        return route.fulfill({status: 412, headers: {ETag: item.etag}, json: {detail: {code: "spec_conflict", message: "다른 창에서 변경했습니다."}}});
      }
      expect(body.version).toBe(ws.version);
      expect(request.headers()["if-match"]).toBe(item.etag);
      ws.version++;
      item = {...item, revision: item.revision + 1, input_version: ws.version, etag: `"spec-r${item.revision + 1}-v${ws.version}"`, payload: body.payload};
      return route.fulfill({json: listing()});
    }
    if (method === "POST" && path === `${prefix}/spec-search` && enabled) {
      const body = request.postDataJSON();
      calls.searches.push(body);
      expect(body.limit).toBe(5);
      const hit = {id: "verified-hit", document_id: "product-evidence", quote: "검증 근거: 출력 전압 0.00100 mV", locator: "제품 시험서 3쪽",
        rrf: 0.025, ranks: {lexical: 1, graph: 2}, compliance: "meets", reason: "요구 수치와 일치"};
      return route.fulfill({json: {groups: {
        verified: [hit],
        references: [{...hit, id: "reference-hit", document_id: "company-reference", quote: "참고 인용: 이전 제안서의 전원 장치", compliance: "unassessed", reason: "참고자료는 증빙 아님"}],
        conflicts: [{...hit, id: "conflict-hit", document_id: "conflicting-evidence", quote: "상충 인용: 출력 전압 조건 불일치", compliance: "does_not_meet", reason: "조건 불일치"}],
      }, degraded: true, reasons: ["dense_unavailable"], generation: "spec-generation-1"}});
    }
    if (method === "POST" && path === `${prefix}/jobs` && enabled) {
      const body = request.postDataJSON();
      calls.jobs.push(body);
      expect(body).toEqual({kind: "spec_index", input_version: ws.version, idempotency_key: expect.any(String)});
      expect(body.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i);
      return route.fulfill({status: 202, json: {
        id: "spec-index-job", notice_no: noticeNo, kind: "spec_index", input_version: ws.version,
        status: "queued", quality: null, parameters: {}, result: null, error: null,
        created_at: "2026-09-11T00:00:00Z", started_at: null, finished_at: null, execution_lane: "external",
      }});
    }
    if (method === "POST" && path === `${prefix}/document-drafts` && options.writing) {
      const body = request.postDataJSON();
      calls.drafts.push(body);
      expect(body.version).toBe(ws.version);
      expect(body).not.toHaveProperty("approved");
      expect(body).not.toHaveProperty("evidence_ids");
      expect(body.draft_id).toBe("proposal");
      expect(body.web_references).toEqual([]);
      ws.inputs.proposal_sections = [{id: body.draft_id, title: body.title, document_kind: body.document_kind,
        text: body.text, references: body.references, web_references: [], review_status: "pending", evidence_ids: []}];
      ws.version++;
      return route.fulfill({json: ws});
    }
    calls.unexpected.push(`${method} ${path}`);
    return route.fulfill({status: 501, json: {detail: {message: "Unexpected mock request; no live API was called."}}});
  });
  return {calls, workspace: ws, item: () => item};
}

async function openWorkbench(page: Page) {
  await page.goto(`/workspace/${noticeNo}`);
  await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
  const workbench = page.getByRole("region", {name: "사양 검토 작업대", exact: true});
  await expect(workbench.getByRole("button", {name: "사양 검토·검색", exact: true})).toHaveAttribute("aria-expanded", "false");
  return workbench;
}

async function expectFits(page: Page, workbench: Locator) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // Check text/control bounds within header rows as well as page-level overflow.
  const header = workbench.getByRole("heading", {name: /전원 장치 · 출력 전압 · 개정/});
  if (await header.count()) {
    const bounds = await header.evaluate(element => {
      const row = element.parentElement!;
      const box = row.getBoundingClientRect();
      const children = Array.from(row.children).map(child => child.getBoundingClientRect());
      return {contained: children.every(rect => rect.left >= box.left - 1 && rect.right <= box.right + 1),
        overlap: children.length > 1 && children[0].right > children[1].left && children[0].bottom > children[1].top && children[1].bottom > children[0].top};
    });
    expect(bounds).toEqual({contained: true, overlap: false});
    await expect.poll(() => workbench.getByText(/입력 버전 \d+ · 미해결 사양/).evaluate(element => {
      const context = element.parentElement!.parentElement!;
      return context.scrollWidth <= context.clientWidth;
    })).toBe(true);
  }
}

for (const width of [390, 1280]) {
  test.describe(`specification mock at ${width}px`, () => {
    const height = width === 1280 ? 800 : 844;
    test.use({viewport: {width, height}});

    test("412 keeps edits and comparison until an explicit fresh edit/save; refresh does not navigate", async ({page, baseURL}, testInfo) => {
      const mock = await mockSpecifications(page, baseURL, {conflictOnce: true});
      const workbench = await openWorkbench(page);
      expect(mock.calls.lists).toBe(0);
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await workbench.getByRole("button", {name: "전원 장치 출력 전압 수정", exact: true}).click();
      const editor = workbench.getByRole("region", {name: "담당자 사양 수정", exact: true});
      await editor.getByRole("textbox", {name: "값", exact: true}).fill("123.450000");
      await editor.getByRole("textbox", {name: "변경 사유", exact: true}).fill("원문 대조 후 교정");
      expect(mock.calls.puts).toHaveLength(0);
      const conflict = page.waitForResponse(response => response.request().method() === "PUT" && response.status() === 412);
      await editor.getByRole("button", {name: "사양 수정 저장", exact: true}).click();
      await conflict;
      const latest = editor.getByRole("complementary", {name: "최신 사양 비교", exact: true});
      await expect(latest.getByText("999.000", {exact: true})).toBeVisible();
      await expect(editor.getByRole("textbox", {name: "값", exact: true})).toHaveValue("123.450000");
      await expect(editor.getByRole("textbox", {name: "변경 사유", exact: true})).toHaveValue("원문 대조 후 교정");
      await expect(editor.getByRole("button", {name: "사양 수정 저장", exact: true})).toBeDisabled();
      expect(mock.calls.puts[0]).toMatchObject({etag: '"spec-r2-v4"', body: {version: 4, payload: {value: "123.450000"}}});
      expect(mock.calls.singles).toBe(2);

      await workbench.getByRole("textbox", {name: "근거 검색어", exact: true}).fill("출력 전압");
      await workbench.getByRole("button", {name: "사양 근거 검색", exact: true}).click();
      await expect(workbench.getByRole("region", {name: "사양 검색 결과", exact: true})).toBeVisible();
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await expect(editor.getByRole("alert")).toContainText("자동 재저장하지 않습니다");
      await expect(editor.getByRole("textbox", {name: "값", exact: true})).toHaveValue("123.450000");
      await expectFits(page, workbench);
      await workbench.screenshot({path: testInfo.outputPath(`conflict-${width}.png`)});
      expect(mock.calls.puts).toHaveLength(1);
      expect(mock.calls.jobs).toHaveLength(0);

      // Explicitly discard/reopen after comparison; never silently rebase the draft ETag.
      await editor.getByRole("button", {name: "수정 취소", exact: true}).click();
      await page.getByText("검토 의견·상태 관리", {exact: true}).click();
      await page.getByRole("button", {name: "최신 상태", exact: true}).click();
      await expect(workbench.getByText("입력 버전 5 · 미해결 사양 1개", {exact: true})).toBeVisible();
      await workbench.getByRole("button", {name: "전원 장치 출력 전압 수정", exact: true}).click();
      await expect(editor.getByRole("textbox", {name: "값", exact: true})).toHaveValue("999.000");
      await editor.getByRole("textbox", {name: "값", exact: true}).fill("123.450000");
      await editor.getByRole("textbox", {name: "변경 사유", exact: true}).fill("최신 사양 비교 후 재검토");
      const readsBeforeSave = mock.calls.workspace;
      await editor.getByRole("button", {name: "사양 수정 저장", exact: true}).click();
      await expect(editor).toBeHidden();
      await expect.poll(() => mock.calls.workspace).toBeGreaterThan(readsBeforeSave);
      await expect(workbench.getByRole("status", {name: "사양 작업 결과", exact: true})).toContainText("승인이 아닙니다");
      expect(mock.calls.puts).toHaveLength(2);
      expect(mock.calls.puts[1]).toEqual({etag: '"spec-r3-v5"', body: {version: 5, payload: {...payload, value: "123.450000"}, note: "최신 사양 비교 후 재검토"}});
      await expect(page).toHaveURL(new RegExp(`/workspace/${noticeNo}#writing$`));
      await expect(workbench.getByRole("button", {name: /승인|제출/})).toHaveCount(0);
      await page.reload();
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await expect(workbench.getByText("123.450000", {exact: true})).toBeVisible();
      expect(mock.workspace.inputs.requirements[0].review_status).toBe("pending");
      expect(mock.workspace.reviews).toEqual([]);
      expect(mock.calls.unexpected).toEqual([]);
      expect(mock.calls.pageErrors).toEqual([]);
    });

    test("groups retain source roles without approval; explicit indexing handles 202 Accepted", async ({page, baseURL}, testInfo) => {
      const mock = await mockSpecifications(page, baseURL);
      const workbench = await openWorkbench(page);
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await expect(workbench.getByText("1000000000000000000.01", {exact: true})).toBeVisible();
      await workbench.getByText("출처 · notice-text", {exact: true}).click();
      await expect(workbench.getByText(`문서 SHA256: ${sha}`, {exact: true})).toBeVisible();
      await expect(workbench.locator("blockquote")).toHaveText(raw);
      await workbench.getByRole("textbox", {name: "근거 검색어", exact: true}).fill("출력 전압 0.00100 mV");
      await workbench.getByRole("combobox", {name: "요구사항", exact: true}).selectOption("req-1");
      expect(mock.calls.searches).toHaveLength(0);
      expect(mock.calls.jobs).toHaveLength(0);
      await workbench.getByRole("button", {name: "사양 근거 검색", exact: true}).click();
      const results = workbench.getByRole("region", {name: "사양 검색 결과", exact: true});
      for (const [group, quote, evaluation] of [
        ["검증된 근거", "검증 근거: 출력 전압 0.00100 mV", "자동 평가: 충족"],
        ["참고자료 · 증빙 아님", "참고 인용: 이전 제안서의 전원 장치", "자동 평가: 미평가"],
        ["상충 자료", "상충 인용: 출력 전압 조건 불일치", "자동 평가: 미충족"],
      ]) {
        const region = results.getByRole("region", {name: group, exact: true});
        await expect(region.locator("blockquote")).toHaveText(quote);
        await expect(region).toContainText(evaluation);
      }
      await expect(results).toContainText("dense_unavailable");
      await expect(results).toContainText("제한된 검색 결과");
      await expect(results).toContainText("spec-generation-1");
      expect(mock.calls.searches).toEqual([{query: "출력 전압 0.00100 mV", requirement_id: "req-1", limit: 5}]);
      await expect(workbench.getByRole("button", {name: /승인|제출/})).toHaveCount(0);
      await expectFits(page, workbench);
      await workbench.screenshot({path: testInfo.outputPath(`groups-${width}.png`)});
      const readsBeforeIndex = mock.calls.workspace;
      const accepted = page.waitForResponse(response => response.url().endsWith("/jobs") && response.request().method() === "POST" && response.status() === 202);
      await workbench.getByRole("button", {name: "사양 색인 생성", exact: true}).click();
      await accepted;
      await expect(workbench.getByRole("status", {name: "사양 작업 결과", exact: true})).toContainText("색인 작업 접수 완료");
      await expect.poll(() => mock.calls.workspace).toBeGreaterThan(readsBeforeIndex);
      await expect(page).toHaveURL(new RegExp(`/workspace/${noticeNo}#writing$`));
      expect(mock.calls.jobs).toHaveLength(1);
      expect(mock.calls.puts).toHaveLength(0);
      expect(mock.workspace.reviews).toEqual([]);
      expect(mock.calls.unexpected).toEqual([]);
      expect(mock.calls.pageErrors).toEqual([]);
    });

    test("disabled environment gives explicit feedback and no mutation controls", async ({page, baseURL}, testInfo) => {
      const mock = await mockSpecifications(page, baseURL, {enabled: false});
      const workbench = await openWorkbench(page);
      expect(mock.calls.lists).toBe(0);
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await expect(workbench.getByText("사양 검토 기능이 활성화되지 않았습니다.", {exact: true})).toBeVisible();
      await expect(workbench.getByRole("button", {name: /사양 색인 생성|사양 수정 저장|사양 근거 검색|승인/})).toHaveCount(0);
      await expect(workbench.getByRole("textbox", {name: "근거 검색어", exact: true})).toHaveCount(0);
      await workbench.getByRole("button", {name: "사양 새로고침", exact: true}).click();
      await expect.poll(() => mock.calls.lists).toBe(2);
      await expectFits(page, workbench);
      await workbench.screenshot({path: testInfo.outputPath(`disabled-${width}.png`)});
      expect(mock.calls.puts).toEqual([]);
      expect(mock.calls.searches).toEqual([]);
      expect(mock.calls.jobs).toEqual([]);
      expect(mock.calls.unexpected).toEqual([]);
      expect(mock.calls.pageErrors).toEqual([]);
    });

    test("search selection prefills a draft reference, with separate insert and save actions", async ({page, baseURL}, testInfo) => {
      const mock = await mockSpecifications(page, baseURL, {writing: true});
      const workbench = await openWorkbench(page);
      await workbench.getByRole("button", {name: "사양 검토·검색", exact: true}).click();
      await workbench.getByRole("textbox", {name: "근거 검색어", exact: true}).fill("전원 장치");
      await workbench.getByRole("button", {name: "사양 근거 검색", exact: true}).click();
      const writer = page.getByRole("region", {name: "문서별 비교 작성", exact: true});
      const excerpt = writer.getByRole("textbox", {name: "참고 발췌문", exact: true});
      const body = writer.getByRole("textbox", {name: "서류 작성 내용", exact: true});
      const verified = workbench.getByRole("region", {name: "검증된 근거", exact: true});
      await verified.getByRole("button", {name: "작성 자료로 선택", exact: true}).click();
      await expect(writer.getByRole("combobox", {name: "참고할 회사 자료", exact: true})).toHaveValue("product-evidence");
      await expect(excerpt).toHaveValue("검증 근거: 출력 전압 0.00100 mV");
      await expect(body).toHaveValue("");
      await expect(writer.getByRole("button", {name: "서류 초안 저장", exact: true})).toBeDisabled();
      expect(mock.calls.drafts).toHaveLength(0);
      await writer.screenshot({path: testInfo.outputPath(`selected-prefill-${width}.png`)});
      const screenshotTarget = width === 1280 ? writer : writer.getByRole("complementary", {name: "작성 참고자료", exact: true});
      await screenshotTarget.evaluate(element => element.scrollIntoView({block: "start"}));
      await page.screenshot({path: testInfo.outputPath(`selection-viewport-${width}x${height}.png`)});
      await expect(writer.getByRole("option", {name: "미확인 제품 근거", exact: true})).toHaveCount(0);
      await expect(writer.getByRole("option", {name: "기간 문제 회사 증빙", exact: true})).toHaveCount(0);
      await expect(workbench.getByRole("region", {name: "상충 자료", exact: true}).getByRole("button", {name: "작성 자료로 선택", exact: true})).toHaveCount(0);
      await writer.getByRole("button", {name: "발췌문 넣기", exact: true}).click();
      await expect(body).toHaveValue("[검증필요] 검증 근거: 출력 전압 0.00100 mV");
      expect(mock.calls.drafts).toHaveLength(0);
      await workbench.getByRole("region", {name: "참고자료 · 증빙 아님", exact: true}).getByRole("button", {name: "작성 자료로 선택", exact: true}).click();
      await expect(excerpt).toHaveValue("참고 인용: 이전 제안서의 전원 장치");
      await expect(body).toHaveValue("[검증필요] 검증 근거: 출력 전압 0.00100 mV");
      await writer.getByRole("button", {name: "발췌문 넣기", exact: true}).click();
      const expectedText = "[검증필요] 검증 근거: 출력 전압 0.00100 mV\n\n[검증필요] 참고 인용: 이전 제안서의 전원 장치";
      await expect(body).toHaveValue(expectedText);
      expect(mock.calls.drafts).toHaveLength(0);
      await expectFits(page, workbench);
      await writer.screenshot({path: testInfo.outputPath(`selected-evidence-${width}.png`)});
      await writer.getByRole("button", {name: "서류 초안 저장", exact: true}).click();
      await expect(writer.getByRole("status")).toContainText("저장 완료 · 검토 대기");
      expect(mock.calls.drafts).toHaveLength(1);
      expect(mock.calls.drafts[0]).toMatchObject({version: 4, text: expectedText, references: [
        {document_id: "product-evidence", quote: "검증 근거: 출력 전압 0.00100 mV"},
        {document_id: "company-reference", quote: "참고 인용: 이전 제안서의 전원 장치"},
      ]});
      await expect(page).toHaveURL(new RegExp(`/workspace/${noticeNo}#writing$`));
      expect(mock.workspace.inputs.documents.find(document => document.id === "company-reference")).toMatchObject({role: "company_reference", confirmed: false});
      expect(mock.workspace.reviews).toEqual([]);
      expect(mock.calls.puts).toEqual([]);
      expect(mock.calls.jobs).toEqual([]);
      expect(mock.calls.unexpected).toEqual([]);
      expect(mock.calls.pageErrors).toEqual([]);
    });
  });
}
