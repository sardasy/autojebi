import {expect, test} from "@playwright/test";

for (const failed of [false, true]) {
  test(`structured HWP ${failed ? "recovery failure" : "warning draft"} remains review pending`, async ({page}) => {
    let generated = false;
    const job = {id:"mock-layout", notice_no:"E2E-LAYOUT", kind:"hwp", input_version:1,
      status:failed ? "failed" : "succeeded", quality:failed ? "normal" : "warning", parameters:{template_key:"proposal_layout_v1"},
      created_at:"2026-09-10T00:00:00Z", error:failed ? {code:"operation_uncertain", message:"한글 저장 응답을 확인하지 못했습니다.", next_action:"Worker 종료와 파일 확인 후 복구하세요."} : null,
      result:failed ? null : {artifact:"draft.hwp", verified:true, warnings:["문서 배치 검토 필요"], required_missing:[], remaining_placeholders:["body_0001"], pages:[{number:1,width:794,height:1122}]}};
    await page.route("**/api/v2/**", async route => {
      const url = new URL(route.request().url());
      const pathname = url.pathname;
      if (pathname.endsWith("/hwp-templates")) return route.fulfill({json:{items:[{template_key:"proposal_layout_v1",name:"제안서 · 실무 서식"}]}});
      if (pathname.endsWith("/hwp-worker")) return route.fulfill({json:{code:generated && failed ? "worker_recovery" : "worker_connected"}});
      if (pathname.endsWith("/worker/health")) return route.fulfill({json:{available:true,state:"idle"}});
      if (pathname.endsWith("/workspace")) return route.fulfill({json:{notice_no:"E2E-LAYOUT",version:1,decision:"pending",ready:false,source_changed:false,
        inputs:{notice:{title:"HWP 서식 회귀",org_name:"검증 기관",close_date:null},company:{},documents:[],requirements:[],checklist:[],proposal_sections:[]},
        blockers:[],next_action:"생성물 검토",jobs:generated ? [job] : [],reviews:[]}});
      if (pathname.endsWith("/hwp-context")) return route.fulfill({json:{input_version:1,values:{proposal_body:"# 검토용 초안"},required_missing:[]}});
      if (pathname.endsWith("/prerequisites")) return route.fulfill({json:{input_version:1,template_key:"proposal_layout_v1",checked_at:"2026-09-10T00:00:00Z",hwp_request_available:true,items:[],required_missing:[],mapping_fields:["proposal_body"]}});
      if (pathname.endsWith("/jobs") && route.request().method() === "POST") {
        expect(route.request().postDataJSON().template_key).toBe("proposal_layout_v1");
        generated = true;
        return route.fulfill({status:202,json:job});
      }
      if (pathname.includes("/pages/")) return route.fulfill({contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64")});
      return route.fulfill({status:404,json:{detail:"Unexpected mock request"}});
    });
    await page.goto("/workspace/E2E-LAYOUT#review");
    await expect(page.getByLabel("HWP 템플릿",{exact:true})).toHaveValue("proposal_layout_v1");
    await page.getByRole("button",{name:"입력값 확인",exact:true}).click();
    await page.getByText("필수조건 점검 · 제안서 · 실무 서식",{exact:true}).click();
    await page.getByRole("button",{name:"필수조건 다시 확인",exact:true}).click();
    await page.getByRole("button",{name:"HWP 생성",exact:true}).click();
    const result = page.getByRole("article").filter({hasText:failed ? "HWP 생성 · 실패" : "HWP 생성 · 완료"});
    await expect(result).toBeVisible();
    await expect(result).toContainText("검토 대기");
    if (failed) {
      await expect(result).toContainText("Worker 종료와 파일 확인 후 복구하세요.");
      await expect(result.getByRole("button",{name:"초안 승인",exact:true})).toHaveCount(0);
    } else {
      await expect(result).toContainText("body_0001");
      await expect(result.getByRole("link",{name:"다운로드",exact:true})).toBeVisible();
      await result.getByText(/한글 페이지 미리보기/).click();
      await expect(result.getByRole("img")).toBeVisible();
    }
    for (const width of [1280,390]) {
      await page.setViewportSize({width,height:800});
      await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({path:`test-results/hwp-layout-${failed ? "failed" : "warning"}-${width}.png`,fullPage:true});
    }
  });
}
