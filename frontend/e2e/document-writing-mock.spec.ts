import {expect,test} from "@playwright/test";
import {Workspace} from "../src/lib/workspace";

test("reviewed source targets become the writing list; issued files stay attachments",async({page})=>{
  const ws:Workspace={notice_no:"WRITING",version:1,decision:"pending",ready:false,source_changed:false,writing_plan_current:false,inputs:{notice:{title:"차량 제어기 개발 용역",org_name:"검증 기관",close_date:null,base_price:null},documents:[{id:"reference",name:"회사 기존 제안서.txt",role:"company_reference",text:"기존 수행계획과 시험 절차",text_origin:"manual",confirmed:false},{id:"notice",name:"공고문.txt",role:"notice_source",text:"① 정성제안서 1부\n② 서약서 1부\n③ 사업자등록증 1부\n가. 가격입찰서 제출",text_origin:"manual",confirmed:false}],requirements:[],proposal_sections:[],checklist:[],company:{},source_reviewed:false,legacy_warning:false},jobs:[],reviews:[],blockers:[],next_action:""};
  await page.route("**/api/v2/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/hwp-templates"))return route.fulfill({json:{items:[]}});
    if(path.endsWith("/workspace"))return route.fulfill({json:ws});
    if(path.endsWith("/writing-plan")){
      const body=route.request().postDataJSON();expect(body.version).toBe(ws.version);
      ws.inputs.writing_plan={items:body.items,reviewed_version:ws.version,reviewed_at:"2026-09-11"};ws.writing_plan_current=true;ws.version++;
      return route.fulfill({json:ws});
    }
    if(path.endsWith("/document-drafts") && route.request().method()==="POST"){
      const body=route.request().postDataJSON();expect(body.version).toBe(ws.version);
      expect(ws.inputs.writing_plan?.items.some(i=>i.id===body.draft_id && i.action==="write")).toBe(true);
      ws.inputs.proposal_sections=ws.inputs.proposal_sections!.filter(s=>s.id!==body.draft_id);
      ws.inputs.proposal_sections.push({...body,id:body.draft_id,review_status:"pending",evidence_ids:[]});ws.version++;
      return route.fulfill({json:ws});
    }
    if(path.endsWith("/download"))return route.fulfill({body:"saved document",contentType:"text/markdown",headers:{"Content-Disposition":"attachment; filename=draft.md"}});
    return route.fulfill({json:{available:true,state:"idle"}});
  });
  await page.goto("/workspace/WRITING#writing");
  const editor=page.getByRole("region",{name:"문서별 비교 작성"});
  await expect(editor.getByLabel("서류 작성 내용")).toHaveCount(0);
  await editor.getByRole("button",{name:"공고 서류 검토로 이동"}).click();
  const review=page.getByRole("region",{name:"작성 대상 검토"});
  await expect(review.getByLabel("사업자등록증 처리")).toHaveValue("attach");
  await expect(review.getByLabel("가격입찰서 처리")).toHaveValue("electronic");
  await review.getByLabel("공고 서류를 검토하고 작성·첨부 대상을 확인했습니다.").check();
  await review.getByRole("button",{name:"확인 완료 · 비교·작성으로 이동"}).click();
  await expect(editor.getByRole("button",{name:"정성제안서 미작성"})).toBeVisible();
  await expect(editor.getByRole("button",{name:"서약서 미작성"})).toBeVisible();
  await expect(editor.getByRole("button",{name:/사업자등록증 미작성|기타서류 미작성|입찰서 미작성/})).toHaveCount(0);
  await editor.getByRole("button",{name:"항목 제목 넣기"}).click();
  await editor.getByLabel("참고할 회사 자료").selectOption("reference");
  await editor.getByLabel("참고 발췌문").fill("기존 수행계획과 시험 절차");
  await editor.getByRole("button",{name:"발췌문 넣기"}).click();
  await editor.getByRole("button",{name:"서약서 미작성"}).click();
  await editor.getByLabel("서류 작성 내용").fill("서약서 검토 초안");
  await editor.getByRole("button",{name:"정성제안서 저장 전"}).click();
  await expect(editor.getByLabel("서류 작성 내용")).toContainText("기존 수행계획");
  await editor.getByRole("button",{name:"서류 초안 저장"}).click();
  await expect(editor.getByRole("status")).toContainText("저장 완료");
  await editor.getByRole("button",{name:"서약서 저장 전"}).click();
  await editor.getByRole("button",{name:"서류 초안 저장"}).click();
  await expect(editor.getByRole("status")).toContainText("저장 완료");
  const download=page.waitForEvent("download");await editor.getByRole("link",{name:"텍스트 초안 다운로드"}).click();expect((await download).suggestedFilename()).toBe("draft.md");
  await page.reload();await editor.getByRole("button",{name:"서약서 저장됨"}).click();
  await expect(editor.getByLabel("서류 작성 내용")).toHaveValue("서약서 검토 초안");
  for(const width of [1280,390]){await page.setViewportSize({width,height:800});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await editor.screenshot({path:`test-results/reviewed-writing-${width}.png`});}
  expect(ws.inputs.documents[0].confirmed).toBe(false);
});
