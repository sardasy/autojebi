import { expect, test } from "@playwright/test";
import path from "node:path";

test.describe("v2 durable workspace", () => {
  test.skip(process.env.E2E_WORKSPACE_V2 !== "true", "opt-in isolated v2 DB only");
  test("prerequisites separate draft permission from qualification and invalidate template checks", async ({page}) => {
    const workspace = {notice_no:"E2E-PREFLIGHT", version:1, decision:"pending", ready:false, source_changed:false,
      inputs:{notice:{title:"필수조건 검증", org_name:"검증 기관", close_date:null}, company:{}, documents:[], requirements:[], checklist:[], source_reviewed:false},
      blockers:["실제 증빙 확인 필요"], next_action:"원문 검토", jobs:[], reviews:[]};
    await page.route("**/api/v2/notices/E2E-PREFLIGHT/workspace", route => route.fulfill({json:workspace}));
    await page.route("**/api/v2/worker/health", route => route.fulfill({json:{available:true, state:"idle", heartbeat_at:null, last_failure:null}}));
    await page.route("**/api/v2/notices/E2E-PREFLIGHT/hwp-context?*", route => route.fulfill({json:{input_version:1, values:{company_name:"검증용"}, required_missing:[]}}));
    await page.route("**/api/v2/notices/E2E-PREFLIGHT/prerequisites?*", route => route.fulfill({json:{
      input_version:1, template_key:new URL(route.request().url()).searchParams.get("template_key"), checked_at:new Date().toISOString(),
      hwp_request_available:true, required_missing:[], mapping_fields:["company_name"], items:[
        {code:"q", title:"정보통신공사업 0036", state:"blocked", detail:"실제 회사 증빙 필요", action:"자격·증빙 검토", target:"documents", blocks_hwp:false},
        {code:"hwp", title:"HWP 접속", state:"checked", detail:"접속과 제출 준비는 별도", action:"생성 결과 검토", target:"review", blocks_hwp:false},
      ],
    }}));
    await page.goto("/workspace/E2E-PREFLIGHT#review");
    const generate = page.getByRole("button", {name:"HWP 생성", exact:true});
    await page.getByRole("button", {name:"입력값 확인", exact:true}).click();
    await expect(generate).toBeDisabled();
    await page.getByRole("button", {name:"필수조건 다시 확인"}).click();
    await expect(generate).toBeEnabled();
    await expect(page.getByRole("heading", {name:"정보통신공사업 0036 · 보완 필요"})).toBeVisible();
    await expect(page.getByRole("status", {name:"필수조건 결과"})).toContainText("제출 준비는 별도 검토");
    await page.getByLabel("HWP 템플릿", {exact:true}).selectOption("proposal");
    await page.getByRole("button", {name:"입력값 확인", exact:true}).click();
    await expect(generate).toBeDisabled();
    await page.getByRole("button", {name:"필수조건 다시 확인"}).click();
    await expect(generate).toBeEnabled();
    await page.setViewportSize({width:1280, height:800});
    await page.screenshot({path:"test-results/prerequisites-desktop.png", fullPage:true});
    await page.setViewportSize({width:390, height:844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path:"test-results/prerequisites-mobile.png", fullPage:true});
    await page.getByRole("button", {name:"자격·증빙 검토"}).click();
    await expect(page.getByRole("tab", {name:"2. 공고 서류 검토"})).toHaveAttribute("aria-selected", "true");
  });
  test("search filters closed notices and preserves save links on mobile", async ({page}) => {
    const current = {notice_no:"E2E-SEARCH-OPEN", title:"실시간 시뮬레이터 신규 공고", org_name:"검증 기관", close_date:"2099-09-14T10:00:00+09:00", already_exists:false, raw:{}};
    await page.route("**/api/v2/notices?*", route => route.fulfill({json:{items:[], has_more:false}}));
    await page.route("**/api/v2/search", route => route.fulfill({json:{items:[current, {...current, notice_no:"OLD", title:"지난 공고", close_date:"2000-01-01T10:00:00+09:00"}], total:2}}));
    await page.route("**/api/v2/notices", route => route.fulfill({json:{notice_no:current.notice_no}}));
    await page.goto("/workspace");
    await page.getByLabel("G2B 공고명", {exact:true}).fill("시뮬레이터");
    await page.getByRole("button", {name:"G2B 라이브 검색"}).click();
    await expect(page.getByText(current.title, {exact:true})).toBeVisible();
    await expect(page.getByText("지난 공고", {exact:true})).toHaveCount(0);
    await page.getByLabel("마감 전 공고만").uncheck();
    await expect(page.getByText("지난 공고", {exact:true})).toBeVisible();
    await page.getByLabel("마감 전 공고만").check();
    await page.getByRole("button", {name:"저장", exact:true}).click();
    await expect(page.getByRole("link", {name:"이미 등록 →"})).toHaveAttribute("href", `/workspace/${current.notice_no}`);
    await page.setViewportSize({width:390, height:844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path:"test-results/workspace-search-mobile.png", fullPage:true});
  });
  test("previous writing is compared, saved and reviewed without becoming evidence", async ({page, request}) => {
    const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
    const no = `E2E-WRITING-${Date.now()}`;
    expect((await request.post(`${api}/v2/notices`, {data: {notice_no: no, title: "네 단계 서류 작성 검증", source: "E2E", raw: {}}})).ok()).toBeTruthy();
    expect((await request.post(`${api}/v2/notices/${no}/initialize`)).ok()).toBeTruthy();
    await page.goto(`/workspace/${no}`);
    await page.getByLabel("파일", {exact: true}).setInputFiles(path.join(process.cwd(), "e2e/fixtures/technical-spec-sample.pdf"));
    await page.getByRole("button", {name: "등록", exact: true}).click();
    await expect(page.getByRole("status", {name: "실행 결과"})).toContainText("파일 등록 완료");
    await page.getByLabel("검토 의견", {exact: true}).fill("합성 자료 비교 검증");
    await page.getByText("본문 · 분석 불가", {exact: true}).click();
    await page.getByLabel("technical-spec-sample.pdf 본문", {exact: true}).fill("이번 공고는 장비 3대를 요구합니다.");
    await page.getByRole("button", {name: "확인된 본문 저장", exact: true}).click();
    await expect(page.getByRole("status", {name: "실행 결과"})).toContainText("저장 완료");
    let state = await (await request.get(`${api}/v2/notices/${no}/workspace`)).json();
    expect((await request.post(`${api}/v2/notices/${no}/requirements`, {data: {
      version: state.version, text: "장비 3대", document_id: state.inputs.documents[0].id,
      quote: "이번 공고는 장비 3대를 요구합니다.", locator: "1페이지", category: "technical",
    }})).ok()).toBeTruthy();
    await page.reload();
    await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
    await page.getByLabel("회사 기존 작성자료", {exact: true}).setInputFiles(path.join(process.cwd(), "e2e/fixtures/technical-spec-sample.pdf"));
    await page.getByRole("button", {name: "작성자료 등록", exact: true}).click();
    await expect(page.getByRole("status", {name: "실행 결과"})).toContainText("기존 작성자료 등록 완료");
    await page.getByLabel("검토 의견", {exact: true}).fill("이전 작성자료의 재사용 초안");
    await page.getByText("본문 · 분석 불가", {exact: true}).click();
    await page.getByLabel("technical-spec-sample.pdf 본문", {exact: true}).fill("이전 사업에서는 장비 2대를 납품했습니다.");
    await page.getByRole("button", {name: "확인된 본문 저장", exact: true}).click();
    await expect(page.getByRole("status", {name: "실행 결과"})).toContainText("저장 완료");
    await page.getByLabel("참고할 원문 인용", {exact: true}).fill("이전 사업에서는 장비 2대를 납품했습니다.");
    await page.getByLabel("이번 공고에 맞춘 작성 내용", {exact: true}).fill("이번 공고에는 장비 3대를 제안합니다. [검증필요]");
    await page.getByRole("button", {name: "비교 작성 초안 저장", exact: true}).click();
    await expect(page.getByRole("status", {name: "실행 결과"})).toContainText("비교 작성 초안 저장 완료");
    await page.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
    await expect(page.getByLabel("제안서 섹션 본문", {exact: true})).toHaveValue("이번 공고에는 장비 3대를 제안합니다. [검증필요]");
    await page.reload();
    await expect(page.getByLabel("제안서 섹션 본문", {exact: true})).toHaveValue(/장비 3대/);
    state = await (await request.get(`${api}/v2/notices/${no}/workspace`)).json();
    expect(state.inputs.proposal_sections[0].review_status).toBe("pending");
    expect(state.inputs.proposal_sections[0].evidence_ids).toEqual([]);
    expect(state.inputs.proposal_sections[0].reference.quote).toContain("장비 2대");
    expect(state.ready).toBe(false);
    await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
    await page.setViewportSize({width: 1280, height: 800});
    await page.screenshot({path: "test-results/writing-desktop.png", fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path: "test-results/writing-mobile.png", fullPage: true});
  });
  test("focused document loop, durable Excel, blocked HWP and mobile layout", async ({page, request}) => {
    const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
    const no = `E2E-WORKSPACE-${Date.now()}`;
    const registration = await request.post(`${api}/v2/notices`, {data: {notice_no: no, title: "검토 작업대 통합 검증", source: "E2E", raw: {ntceInsttNm: "검증기관", bidClseDt: "2026-12-01 10:00:00"}}});
    expect(registration.ok()).toBeTruthy();
    await page.setViewportSize({width: 1280, height: 800});
    await page.goto(`/workspace/${no}`);
    await page.getByRole("button", {name: "검토 시작", exact: true}).click();
    await expect(page.getByRole("heading", {name: "검토 작업대 통합 검증"})).toBeVisible();
    await page.getByRole("textbox", {name: "검토 의견", exact: true}).fill("E2E: 검토용이며 실제 참가 결정 아님");
    await expect(page.getByRole("combobox", {name: "참가 결정", exact: true})).toHaveCount(0);
    await page.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
    await page.getByRole("button", {name: "Excel 생성", exact: true}).click();
    await expect(page.getByText("Excel 생성 · 완료", {exact: true})).toBeVisible({timeout: 30000});
    const download = page.waitForEvent("download");
    await page.getByRole("link", {name: "다운로드", exact: true}).click();
    expect((await download).suggestedFilename()).toContain("requirements.xlsx");
    await expect(page.getByRole("button", {name: "알림 미리보기", exact: true})).toHaveCount(0);
    await page.getByRole("button", {name: "입력값 확인", exact: true}).click();
    await expect(page.getByText(/필수 누락/).first()).toBeVisible();
    await page.getByRole("button", {name: "필수조건 다시 확인", exact: true}).click();
    await expect(page.getByRole("status", {name: "필수조건 결과"})).toContainText("HWP 생성 전 보완 필요");
    await expect(page.getByRole("button", {name: "HWP 생성", exact: true})).toBeDisabled();
    await page.getByRole("button", {name: "템플릿 필드 검사", exact: true}).click();
    await expect(page.getByText("템플릿 필드 검사 · 차단", {exact:true})).toBeVisible({timeout:30000});
    // Direct requests still record blocked attempts; the UI prevents a known-invalid request.
    const currentWorkspace = await (await request.get(`${api}/v2/notices/${no}/workspace`)).json();
    expect((await request.post(`${api}/v2/notices/${no}/jobs`, {data: {
      kind: "hwp", input_version: currentWorkspace.version, template_key: "bid_form", idempotency_key: `blocked-${no}`,
    }})).ok()).toBeTruthy();
    await page.getByRole("button", {name: "최신 상태", exact: true}).click();
    await expect(page.getByText("HWP 생성 · 차단", {exact: true})).toBeVisible({timeout: 30000});
    await page.reload();
    await expect(page.getByText("HWP 생성 · 차단", {exact: true})).toBeVisible();
    expect((await (await request.get(`${api}/v2/notices/${no}/workspace`)).json()).decision).toBe("pending");
    await page.screenshot({path: "test-results/workspace-desktop.png", fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path: "test-results/workspace-mobile.png", fullPage: true});
  });
  test("stale review is rejected and rejected Excel can be regenerated", async ({page, context, request}) => {
    const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
    const no = `E2E-REVIEW-${Date.now()}`;
    expect((await request.post(`${api}/v2/notices`, {data: {notice_no: no, title: "검토 충돌 및 복구 검증", source: "E2E", raw: {}}})).ok()).toBeTruthy();
    expect((await request.post(`${api}/v2/notices/${no}/initialize`)).ok()).toBeTruthy();
    await page.goto(`/workspace/${no}`);
    await page.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
    await page.getByRole("button", {name: "Excel 생성", exact: true}).click();
    await expect(page.getByText("Excel 생성 · 완료", {exact: true})).toBeVisible({timeout: 30000});
    const stale = await context.newPage();
    try {
      await stale.goto(`/workspace/${no}`);
      await stale.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
      await expect(stale.getByRole("button", {name: "반려", exact: true})).toBeVisible();
      await page.getByRole("textbox", {name: "검토 의견", exact: true}).fill("첫 창에서 원본 확인");
      await page.getByRole("button", {name: "초안 승인", exact: true}).click();
      await expect(page.getByText("검토 상태: 승인", {exact: true})).toBeVisible();
      await stale.getByRole("textbox", {name: "검토 의견", exact: true}).fill("오래된 창의 검토");
      await stale.getByRole("button", {name: "반려", exact: true}).click();
      await expect(stale.getByRole("status", {name: "실행 결과"})).toContainText("다른 창에서 검토 상태가 변경되었습니다");
      await stale.getByRole("button", {name: "최신 상태", exact: true}).click();
      await expect(stale.getByText("검토 상태: 승인", {exact: true})).toBeVisible();
      await stale.getByRole("button", {name: "반려", exact: true}).click();
      await expect(stale.getByText("검토 상태: 반려", {exact: true})).toBeVisible();
      await stale.getByRole("button", {name: "복구·재생성", exact: true}).click();
      await expect(stale.getByText("Excel 생성 · 완료", {exact: true})).toHaveCount(2, {timeout: 30000});
      const ws = await (await request.get(`${api}/v2/notices/${no}/workspace`)).json();
      expect(ws.version).toBe(1);
      const replacement = ws.jobs.find((job: {parameters: {recovery_of?: string}}) => job.parameters.recovery_of);
      expect(replacement.status).toBe("succeeded");
      expect((await request.get(`${api}/v2/jobs/${replacement.id}/download`)).ok()).toBeTruthy();
    } finally {await stale.close();}
  });
  test("unfetched XLS remains visible and manual source linking survives reload", async ({page, request}) => {
    const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
    const no = `E2E-SOURCE-INVENTORY-${Date.now()}`;
    expect((await request.post(`${api}/v2/notices`, {data: {
      notice_no: no, title: "첨부 누락 및 수동 복구 검증", source: "E2E",
      raw: {ntceSpecFileNm1: "물품명세서.xls", ntceSpecDocUrl1: "https://www.g2b.go.kr/example/specification.xls"},
    }})).ok()).toBeTruthy();
    expect((await request.post(`${api}/v2/notices/${no}/initialize`)).ok()).toBeTruthy();
    await page.setViewportSize({width: 1280, height: 800});
    await page.goto(`/workspace/${no}`);
    const inventory = page.getByRole("table", {name: "나라장터 첨부 목록", exact: true});
    await expect(inventory.getByText("물품명세서.xls", {exact: true})).toBeVisible();
    await expect(inventory.getByText("파일 미확보", {exact: true})).toBeVisible();
    await expect(page.getByRole("button", {name: "원문 전체 대조 확인", exact: true})).toBeDisabled();
    const rejected = await request.post(`${api}/v2/notices/${no}/source-review`, {data: {
      version: 1, text: "confirmed", note: "누락 파일이 있는 합성 테스트 공고",
    }});
    expect(rejected.status()).toBe(409);
    await page.getByLabel("파일", {exact: true}).setInputFiles(path.join(process.cwd(), "e2e/fixtures/technical-spec-sample.pdf"));
    await page.getByRole("button", {name: "등록", exact: true}).click();
    await expect(page.getByRole("status", {name: "실행 결과"})).toContainText("파일 등록 완료");
    await page.getByRole("textbox", {name: "검토 의견", exact: true}).fill("합성 E2E 자료의 수동 원문 연결 검증, 실제 공고 승인 아님");
    await page.getByRole("combobox", {name: "technical-spec-sample.pdf 나라장터 첨부 연결", exact: true}).selectOption("1");
    await page.getByRole("button", {name: "technical-spec-sample.pdf 첨부 연결 저장", exact: true}).click();
    await expect(inventory.getByText("본문 미확인", {exact: true})).toBeVisible();
    await page.getByText("본문 · 분석 불가", {exact: true}).click();
    await page.getByRole("textbox", {name: "technical-spec-sample.pdf 본문", exact: true}).fill("합성 E2E 원문 본문. 실제 입찰 자료가 아닙니다.");
    await page.getByRole("button", {name: "확인된 본문 저장", exact: true}).click();
    await expect(inventory.getByText("본문 확보", {exact: true})).toBeVisible();
    await page.reload();
    await expect(inventory.getByText("본문 확보", {exact: true})).toBeVisible();
    const ws = await (await request.get(`${api}/v2/notices/${no}/workspace`)).json();
    expect(ws.source_attachments[0].document_ids).toHaveLength(1);
    expect(ws.inputs.source_reviewed).toBe(false);
    expect(ws.ready).toBe(false);
    await page.screenshot({path: "test-results/source-inventory-desktop.png", fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path: "test-results/source-inventory-mobile.png", fullPage: true});
  });
});
