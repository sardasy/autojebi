import {expect,test} from "@playwright/test";

test("company registry upload, expiry edit, history and soft-disable",async({page},testInfo)=>{
  let asset:Record<string,unknown>|null=null;
  await page.route("**/api/v2/company-assets**",async route=>{
    const request=route.request();const path=new URL(request.url()).pathname;
    if(path.endsWith("/history"))return route.fulfill({json:{items:[{version:2,note:"시험 자료 사용 중지",created_at:"2026-09-11T00:00:00Z"}]}});
    if(request.method()==="POST"){
      expect(request.headers()["content-type"]).toContain("multipart/form-data");
      expect(request.postData()).toContain("TEST ONLY");
      asset={id:"asset",version:1,role:"company_evidence",validity:"expiring",file:{name:"test.pdf",sha256:"synthetic",size:12},details:{title:"시험 증빙",category:"business_registration",subject_business_number:"0000000000",issued_on:"2026-09-01",expires_on:"2026-09-20",no_expiry:false,active:true}};
      return route.fulfill({json:asset,status:201});
    }
    if(request.method()==="PUT"){
      const body=request.postDataJSON();expect(body.version).toBe(1);
      expect(body.details.active).toBe(false);expect(body.note).toBe("시험 자료 사용 중지");
      asset={...asset,version:2,details:body.details,validity:"disabled"};
      return route.fulfill({json:asset});
    }
    return route.fulfill({json:{items:asset?[asset]:[],page:1,has_more:false,alerts:{expiring:asset?1:0}}});
  });
  await page.goto("/admin#assets");
  await page.getByRole("button",{name:"회사 자료 보관소",exact:true}).click();
  await page.getByRole("button",{name:"자료 등록",exact:true}).click();
  const modal=page.getByRole("dialog",{name:"중앙 자료 등록"});
  await modal.getByLabel("자료명",{exact:true}).fill("시험 증빙");
  await modal.getByLabel("문서 주체 사업자번호").fill("0000000000");
  await modal.getByLabel("발급일",{exact:true}).fill("2026-09-01");
  await modal.getByLabel("만료일",{exact:true}).fill("2026-09-20");
  await modal.getByLabel("원본 파일",{exact:true}).setInputFiles({name:"test.pdf",mimeType:"application/pdf",buffer:Buffer.from("TEST ONLY")});
  await modal.getByRole("button",{name:"저장",exact:true}).click();
  await expect(modal).toBeHidden();
  await expect(page.getByRole("table",{name:"중앙 회사자료"})).toContainText("시험 증빙");
  await page.getByRole("button",{name:"시험 증빙 수정"}).click();
  const edit=page.getByRole("dialog",{name:"중앙 자료 수정"});
  await edit.getByLabel("활성 자료").uncheck();
  await edit.getByLabel("변경 사유").fill("시험 자료 사용 중지");
  await edit.getByRole("button",{name:"저장",exact:true}).click();
  await expect(edit).toBeHidden();
  await page.getByRole("button",{name:"이력",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"중앙 자료 변경 이력"})).toContainText("시험 자료 사용 중지");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button",{name:"이력",exact:true})).toBeFocused();
  for(const width of [1280,390]){
    await page.setViewportSize({width,height:800});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole("region",{name:"회사 자료 보관소"}).screenshot({path:testInfo.outputPath(`company-assets-${width}.png`)});
  }
});

test("one-click company attachment remains unconfirmed and refreshes workspace",async({page})=>{
  const ws={notice_no:"ASSET-E2E",version:1,decision:"pending",ready:false,source_changed:false,inputs:{notice:{title:"TEST ONLY central assets",org_name:"Test",close_date:null,base_price:null},company:{},documents:[] as object[],requirements:[],proposal_sections:[],checklist:[],source_reviewed:false,legacy_warning:false},jobs:[],reviews:[],blockers:[],next_action:""};
  let links=0;
  await page.route("**/api/workspace-session",route=>route.fulfill({json:{enabled:false,actor:null}}));
  await page.route("**/api/v2/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/workspace"))return route.fulfill({json:ws});
    if(path.endsWith("/hwp-templates"))return route.fulfill({json:{items:[]}});
    if(path.endsWith("/company-assets/asset")){
      expect(route.request().postDataJSON()).toEqual({version:1,asset_version:3});links++;
      ws.version=2;ws.inputs.documents=[{id:"doc",name:"시험 증빙.pdf",role:"company_evidence",confirmed:false,text:"",text_origin:"unread",company_asset:{id:"asset",version:3,expires_on:"2026-09-20",no_expiry:false,stale:false}}];
      return route.fulfill({json:ws});
    }
    if(path.endsWith("/company-assets"))return route.fulfill({json:{items:[{id:"asset",version:3,role:"company_evidence",details:{title:"시험 증빙",category:"business_registration",active:true,subject_business_number:"0000000000",expires_on:"2026-09-20"},validity:"expiring",file:{name:"시험 증빙.pdf"}}],page:1,has_more:false,alerts:{expiring:1}}});
    return route.fulfill({json:{available:true,state:"idle"}});
  });
  await page.goto("/workspace/ASSET-E2E#documents");
  // With no source text, the program opens source setup by default.
  await expect(page.locator("#source-details")).toHaveAttribute("open", "");
  await page.getByText("원문·증빙 파일 관리 · 0개",{exact:true}).click();
  await page.getByRole("button",{name:"중앙 회사자료 연결",exact:true}).click();
  await page.getByRole("button",{name:"시험 증빙 연결"}).click();
  await expect(page.getByRole("status",{name:"중앙 자료 결과"})).toContainText("연결 완료");
  await expect(page.getByText("회사 증빙 · 미확인",{exact:true})).toBeVisible();
  await expect(page.getByText("중앙 자료 v3 · 만료일 2026-09-20",{exact:true})).toBeVisible();
  expect(links).toBe(1);
});
