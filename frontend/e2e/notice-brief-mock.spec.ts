import {expect,test} from "@playwright/test";

test("source brief is visible and AI candidate noise stays behind history", async ({page}) => {
  let writes = 0;
  await page.route("**/api/v2/**", async route => {
    if (route.request().method() !== "GET") writes++;
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/hwp-templates")) return route.fulfill({json:{items:[]}});
    if (path.endsWith("/workspace")) return route.fulfill({json:{notice_no:"BRIEF",version:3,decision:"pending",ready:false,source_changed:false,
      inputs:{notice:{title:"차량 제어기 개발·제작 용역",org_name:"검증 기관",close_date:null},company:{},documents:[
        {id:"source",name:"입찰공고.hwp",role:"notice_source",text:"① 사업자등록증 사본 1부\n② 법인등기부등본(법인일 경우) 1부\n\n전자입찰서 제출 마감일시: 2026.09.22. 10:00\n\n계약기간: 계약일~2026.11.30.\n\n사업예산: 70,000,000원(부가세 포함)",confirmed:false},
        {id:"rfp",name:"제안요청서.hwp",role:"notice_source",text:"과업기한: 계약일로부터 50일 이내",confirmed:false},
      ],requirements:[],proposal_sections:[],checklist:[]},blockers:["사람 검토 필요"],next_action:"원문 대조",reviews:[],
      jobs:[{id:"analysis",kind:"analyze",input_version:3,status:"failed",quality:null,created_at:"2026-09-11T00:00:00Z",error:{code:"unverified_quote",message:"AI 인용 검증에 실패한 항목",next_action:"후보 채택"},result:{quote_diagnostics:[{candidate_id:"0",status:"mismatch",requirement:{text:"AI 미확인 주장",quote:"없는 인용",document_id:"source"},matches:[]}]}}]}});
    return route.fulfill({json:{available:true,state:"idle"}});
  });
  await page.goto("/workspace/BRIEF#documents");
  const brief = page.getByRole("region",{name:"공고 핵심 사항"});
  await expect(brief.getByRole("heading",{name:"제출서류",exact:true})).toBeVisible();
  await expect(brief).toContainText("법인일 경우");
  await expect(brief).toContainText("2026.09.22. 10:00");
  await expect(brief).toContainText("50일 이내");
  await expect(page.getByRole("region",{name:"AI 인용 복구"})).toBeHidden();
  for (const message of await page.getByText("AI 인용 검증에 실패한 항목",{exact:false}).all()) await expect(message).toBeHidden();
  await page.getByRole("button",{name:"공고 핵심 확인"}).click();
  await expect(brief).toBeFocused();
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:800});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:`test-results/notice-brief-${width}.png`,fullPage:true});
  }
  await page.getByText("분석·작업 이력",{exact:true}).click();
  await expect(page.getByRole("region",{name:"AI 인용 복구"})).toBeVisible();
  expect(writes).toBe(0);
});
