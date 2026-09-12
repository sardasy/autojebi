import {expect, test} from "@playwright/test";

test("failed analysis candidates can be adopted without approval; source needs stay blocked", async ({page}) => {
  let version = 9;
  let adopted = false;
  const diagnostic = {candidate_id:"0", status:"whitespace", requirement:{text:"납기 확인",quote:"납기\n90일",document_id:"source",locator:"1절",category:"schedule",mandatory:true}, matches:[{start:0,end:6,quote:"납기 90일"}]};
  await page.route("**/api/v2/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/hwp-templates")) return route.fulfill({json:{items:[]}});
    if (path.endsWith("/workspace")) return route.fulfill({json:{notice_no:"E2E-RECOVERY",version,decision:"pending",ready:false,source_changed:false,
      source_needs:[{id:"need",name:"제안요청서",state:"missing",note:"",mentions:[]}],
      inputs:{notice:{title:"인용 복구 검증",org_name:"검증 기관",close_date:null},documents:[{id:"source",name:"공고 원문",role:"notice_source",text:"납기 90일",confirmed:false}],requirements:adopted ? [{id:"req",...diagnostic.requirement,quote:"납기 90일",review_status:"pending",compliance:"unassessed"}] : [],company:{},checklist:[],proposal_sections:[]},
      blockers:["제안요청서 확보 필요"],next_action:"원문 대조",reviews:[],
      jobs:[{id:"analysis",kind:"analyze",input_version:9,status:"failed",quality:null,created_at:"2026-09-10T00:00:00Z",execution_lane:"external",error:{code:"unverified_quote",message:"인용 확인 필요",next_action:"원문 대조"},result:{quote_diagnostics:[diagnostic]}}]}});
    if (path.endsWith("/adopt-requirements")) {
      const body = route.request().postDataJSON();
      expect(body.version).toBe(9);
      expect(body.items[0]).toEqual({candidate_id:"0",quote:"납기 90일",start:0,locator:"1절"});
      expect(body.items[0].review_status).toBeUndefined();
      adopted = true; version++;
      return route.fulfill({json:{}});
    }
    return route.fulfill({json:{available:true,state:"idle",code:"worker_connected"}});
  });
  await page.goto("/workspace/E2E-RECOVERY#documents");
  await page.getByText("분석·작업 이력",{exact:true}).click();
  await page.getByText("공백 차이 · 납기 확인",{exact:true}).click();
  await page.getByLabel("채택 의견",{exact:true}).fill("원문 위치 확인");
  await page.getByRole("button",{name:"이 후보 채택",exact:true}).click();
  await expect(page.getByText(/입력 버전 10/)).toBeVisible();
  await page.locator("summary").filter({hasText:"요구사항 분석 · 실패"}).click();
  await expect(page.getByRole("article")).toContainText("요구사항 분석 · 실패");
  await page.getByText("원문·상세 검토",{exact:true}).click();
  await expect(page.getByText("제안요청서 · 확보·해당 여부 확인 필요",{exact:true})).toBeVisible();
  await expect(page.getByRole("article")).toContainText("기존 항목과 중복");
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:800});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:`test-results/recovery-${width}.png`,fullPage:true});
  }
});
