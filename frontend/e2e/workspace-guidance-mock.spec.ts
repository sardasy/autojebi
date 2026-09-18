import {expect, test} from "@playwright/test";

test("one next action advances attachment preparation without auto-running analysis", async ({page}) => {
  let applied = false;
  const mutations: string[] = [];
  let prerequisiteReads = 0;
  const doc = {id:"source", name:"과업지시서.pdf", role:"notice_source", attachment_index:1, text:""};
  await page.route("**/api/v2/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") mutations.push(path);
    if (path.endsWith("/hwp-templates")) return route.fulfill({json:{items:[]}});
    if (path.endsWith("/prerequisites")) {
      prerequisiteReads++;
      return route.fulfill({json:{input_version:applied ? 2 : 1,
        template_key:new URL(route.request().url()).searchParams.get("template_key"),
        checked_at:"2026-09-11T00:00:00Z",hwp_request_available:false,
        required_missing:["proposal.body"],mapping_fields:[],items:[{
          code:"draft_missing",title:"제안서 본문",state:"blocked",detail:"검토용 초안이 없습니다.",
          action:"초안 작성",target:"writing",blocks_hwp:true,
        }]}});
    }
    if (path.endsWith("/workspace")) return route.fulfill({json:{notice_no:"E2E-GUIDANCE",version:applied ? 2 : 1,decision:"pending",ready:false,source_changed:false,
      inputs:{notice:{title:"EV플랫폼 차량 전용 가감속 제어기 시제품 개발·제작 용역",org_name:"검증 기관",close_date:null},company:{},documents:applied ? [doc] : [],requirements:[],proposal_sections:[],checklist:[]},
      source_attachments:[{index:1,name:doc.name,url:"https://www.g2b.go.kr/file/1",document_ids:applied ? [doc.id] : [],state:applied ? "unread" : "missing"}],
      blockers:["원문 대조 필요"],next_action:"원문 대조 필요",reviews:[],jobs:[{id:"fetch",kind:"fetch",input_version:1,status:"succeeded",quality:null,error:null,created_at:"2026-09-11T00:00:00Z",result:{documents:[doc]}}]}});
    if (path.endsWith("/apply")) {
      expect(route.request().postDataJSON()).toEqual({version:1}); applied = true;
      return route.fulfill({json:{}});
    }
    return route.fulfill({json:{available:true,state:"idle"}});
  });
  await page.goto("/workspace/E2E-GUIDANCE");
  const next = page.getByRole("region",{name:"지금 할 작업"});
  await expect(next.getByRole("button")).toHaveCount(1);
  await expect(next).toContainText("다운로드한 첨부 반영");
  await expect(page.getByText("다운로드 완료 · 반영 대기",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"첨부 가져오기",exact:true})).toBeHidden();
  await expect(page.getByRole("region",{name:"공고 원문 미리보기"})).toHaveCount(0);
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:800});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const bounds = await next.boundingBox();
    expect(bounds!.y + bounds!.height).toBeLessThan(800);
    await page.screenshot({path:`test-results/workspace-guidance-${width}.png`,fullPage:true});
  }
  await next.getByRole("button",{name:"다운로드한 첨부 반영"}).click();
  await expect(next).toContainText("원문 본문 추출");
  expect(mutations).toEqual(["/api/v2/notices/E2E-GUIDANCE/jobs/fetch/apply"]);
  await page.getByText("원문·증빙 파일 관리 · 1개",{exact:true}).click();
  await expect(page.getByRole("button",{name:"등록",exact:true})).toBeVisible();
  await page.getByRole("tab",{name:"3. 비교·작성"}).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab",{name:"4. 서류 확인"})).toBeFocused();
  await expect(page.getByRole("status",{name:"필수조건 결과"})).toContainText("HWP 생성 전 보완 필요");
  await expect(page.getByText("제안서 본문: 검토용 초안이 없습니다.", {exact:true})).toBeVisible();
  expect(prerequisiteReads).toBeGreaterThan(0);
  const readsBeforeRefresh = prerequisiteReads;
  await page.getByRole("button",{name:"필수조건 다시 확인"}).click();
  await expect.poll(()=>prerequisiteReads).toBeGreaterThan(readsBeforeRefresh);
  await expect(page.getByRole("status",{name:"필수조건 결과"})).toContainText("HWP 생성 전 보완 필요");
  expect(mutations).toEqual(["/api/v2/notices/E2E-GUIDANCE/jobs/fetch/apply"]);
});
