import {expect, test} from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {createHash} from "node:crypto";
import type {Workspace, WorkspaceJob} from "../src/lib/workspace";

test.describe.configure({retries:0});

test("PLECS real notice: draft PDF to reviewed downloads without paid calls or approval", async ({page}) => {
  test.skip(process.env.E2E_PLECS_DOCUMENT !== "true", "Explicit real-notice document opt-in");
  test.setTimeout(300_000);
  page.setDefaultTimeout(25000);
  const no = "R26BK01706511-000";
  const filename = "plecs-bid-draft-20260910.pdf";
  const root = path.resolve(process.cwd(), "..");
  const source = path.join(root, "data/workspace/preparation", no, filename);
  const output = path.join(root,"data/workspace/plecs-document-e2e", new Date().toISOString().replace(/[:.]/g,"-"));
  await fs.mkdir(output,{recursive:true});
  const report: {notice_no:string; steps:string[]; jobs:unknown[]; downloads:unknown[]; final?:unknown; error?:string} = {notice_no:no,steps:[],jobs:[],downloads:[]};
  const prefix = `/api/v2/notices/${no}`;
  const current = async ():Promise<Workspace> => {
    const response = await page.request.get(`${prefix}/workspace`);
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const runJob = async (kind:string, label:string) => {
    const previous = new Set((await current()).jobs.map(j=>j.id));
    const accepted = page.waitForResponse(r => r.url().endsWith(`${prefix}/jobs`) && r.request().method() === "POST" && r.request().postDataJSON()?.kind === kind);
    await page.getByRole("button",{name:label,exact:true}).click();
    const response = await accepted;
    expect(response.ok()).toBeTruthy();
    const {id} = await response.json();
    let job:WorkspaceJob | undefined;
    await expect.poll(async () => {
      job = (await current()).jobs.find(j => j.id === id);
      return job && !["queued","running"].includes(job.status);
    },{timeout:150000,intervals:[1000,2000]}).toBeTruthy();
    report.jobs.push({id:job!.id,kind,status:job!.status,quality:job!.quality,error:job!.error,reused:previous.has(id)});
    expect(job!.status,JSON.stringify(job!.error)).toBe("succeeded");
    return job!;
  };
  const status = page.getByRole("status",{name:"실행 결과"});
  try {
    const before = await current();
    await fs.writeFile(path.join(output,"before.json"),JSON.stringify(before,null,2));
    expect(before.source_changed).toBe(false);
    expect(before.jobs.some(j => ["queued","running"].includes(j.status))).toBe(false);
    await page.goto("/workspace");
    await page.getByLabel("공고 검색",{exact:true}).fill(no);
    await page.getByRole("button",{name:"공고 검색 실행",exact:true}).click();
    await page.locator(`a[href="/workspace/${no}"]`).click();
    await expect(page.getByRole("heading",{level:1})).toContainText("RT Box 2");
    await page.getByLabel("검토 의견",{exact:true}).fill("PLECS 작성 문서 E2E 검증. 해당 공고의 검토용 작성자료이며 자격·공급 확약 또는 제출 승인 아님.");
    await page.getByRole("button",{name:"PDF 원본",exact:true}).click();
    const preview = page.getByRole("region",{name:"공고 원문 미리보기"});
    await expect(preview.getByRole("img")).toBeVisible();
    await expect(preview).toContainText("1 / 6");
    await preview.getByRole("button",{name:"다음 페이지",exact:true}).click();
    await expect(preview.getByRole("img")).toHaveAttribute("alt",/2페이지/);
    report.steps.push("저장 공고 검색·상세 진입·공식 공고 PDF 1/2페이지 미리보기");
    await page.getByRole("tab",{name:"3. 비교·작성",exact:true}).click();
    if (!before.inputs.documents.some(d => d.name === filename)) {
      await page.getByLabel("회사 기존 작성자료",{exact:true}).setInputFiles(source);
      await page.getByRole("button",{name:"작성자료 등록",exact:true}).click();
      await expect(status).toContainText("기존 작성자료 등록 완료");
    }
    let state = await current();
    let reference = state.inputs.documents.find(d => d.name === filename)!;
    expect(reference.role).toBe("company_reference");
    expect(reference.confirmed).toBe(false);
    if (!reference.text) {
      await runJob("extract","본문 추출");
      const article = page.locator("article").filter({has:page.getByText("본문 추출 · 완료",{exact:true})}).first();
      await article.getByRole("button",{name:"결과 반영",exact:true}).click();
      await expect(status).toContainText("검토 대상으로 반영 완료");
      state = await current();
      reference = state.inputs.documents.find(d => d.name === filename)!;
    }
    expect(reference.text).toContain("[페이지 15]");
    expect(reference.text).toContain("USB");
    const incoming = page.waitForEvent("download");
    await page.getByRole("link",{name:filename,exact:true}).click();
    const downloaded = path.join(output,filename);
    await (await incoming).saveAs(downloaded);
    expect(createHash("sha256").update(await fs.readFile(downloaded)).digest("hex")).toBe(createHash("sha256").update(await fs.readFile(source)).digest("hex"));
    report.steps.push("15쪽 초안 참고자료 등록·본문 추출·원본 다운로드 바이트 일치, 증빙 자동 승인 없음");

    const text = "[검증필요] 공고의 계약일로부터 30일 이내 납품 조건을 기준으로 일정을 검토합니다. 요청서의 계약·발주 후 1개월 표현과 기준일 차이는 발주기관 확인 후 확정하며, 제조사 공급 가능일 확인 전 납기를 확약하지 않습니다.";
    if (!state.inputs.proposal_sections?.some(s => s.text === text)) {
      const requirement = state.inputs.requirements.find(r => r.text.includes("납품기한"))!;
      expect(requirement).toBeTruthy();
      const quote = "계약일로부터 30일 이내";
      expect(reference.text).toContain(quote);
      await page.getByRole("combobox",{name:"이번 공고 요구사항",exact:true}).selectOption(requirement.id);
      await page.getByRole("combobox",{name:"기존 작성자료",exact:true}).selectOption(reference.id);
      await page.getByLabel("참고할 원문 인용",{exact:true}).fill(quote);
      await page.getByLabel("이번 공고에 맞춘 작성 내용",{exact:true}).fill(text);
      await page.getByRole("button",{name:"비교 작성 초안 저장",exact:true}).click();
      await expect(status).toContainText("비교 작성 초안 저장 완료");
    }
    await page.getByRole("tab",{name:"4. 서류 확인",exact:true}).click();
    await page.reload();
    await page.getByLabel("검토 의견",{exact:true}).fill("문서 E2E 확인. 제출·증빙·초안 승인 아님.");
    expect((await current()).inputs.proposal_sections?.find(s=>s.text===text)?.review_status).toBe("pending");
    report.steps.push("납기 표현 차이를 원문 요구사항과 연결해 검토 대기 저장, 새로고침 후 유지");
    state = await current();
    await runJob("verify","누락 검사");
    for (const [name,kind,file] of [["Excel 생성","excel","requirements.xlsx"],["검토 패키지","package","review-package.zip"]]) {
      const job = await runJob(kind,name);
      const article = page.locator("article").filter({has:page.locator(`a[href="/api/v2/jobs/${job.id}/download"]`)});
      await expect(article.getByText(`${name} · 완료`,{exact:true})).toBeVisible();
      const transfer = page.waitForEvent("download");
      await article.getByRole("link",{name:"다운로드",exact:true}).click();
      await (await transfer).saveAs(path.join(output,file));
      const data = await fs.readFile(path.join(output,file));
      const sha256 = createHash("sha256").update(data).digest("hex");
      expect(sha256).toBe((job.result as {sha256?:string})?.sha256);
      report.downloads.push({kind,job_id:job.id,file,bytes:data.length,sha256});
    }
    report.steps.push("누락 검사·Excel·검토 패키지 생성 및 실제 다운로드, 서버 파일 해시 일치");
    await page.getByRole("button",{name:"필수조건 다시 확인",exact:true}).click();
    await expect(page.getByRole("status",{name:"필수조건 결과"})).toContainText("HWP 생성 전 보완 필요");
    await page.getByRole("button",{name:"입력값 확인",exact:true}).click();
    await expect(page.getByRole("button",{name:"HWP 생성",exact:true})).toBeDisabled();
    state = await current();
    expect(state.ready).toBe(false);
    expect(state.decision).toBe(before.decision);
    expect(state.inputs.requirements).toEqual(before.inputs.requirements);
    for (const d of before.inputs.documents) expect(state.inputs.documents.find(x=>x.id===d.id)).toEqual(d);
    for (const s of before.inputs.proposal_sections || []) expect(state.inputs.proposal_sections?.find(x=>x.id===s.id)).toEqual(s);
    for (const review of before.reviews) expect(state.reviews.find(r=>r.id===review.id)).toEqual(review);
    const paid = (w:Workspace)=>w.jobs.filter(j=>["analyze","proposal"].includes(j.kind)).map(j=>j.id).sort();
    expect(paid(state)).toEqual(paid(before));
    expect(state.jobs.some(j=>["queued","running"].includes(j.status))).toBe(false);
    await page.setViewportSize({width:1280,height:800});
    await page.screenshot({path:path.join(output,"desktop.png")});
    await page.setViewportSize({width:390,height:844});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:path.join(output,"mobile.png")});
    report.steps.push("HWP 사전 차단·기존 원문/요구사항/결정/검토 이력 보존·추가 유료 호출 없음·모바일 넘침 없음");
    report.final = {version:state.version,ready:state.ready,requirements:state.inputs.requirements.length,sections:state.inputs.proposal_sections?.length,blockers:state.blockers};
    await fs.writeFile(path.join(output,"after.json"),JSON.stringify(state,null,2));
  } catch (error) {
    report.error=String(error);
    await page.screenshot({path:path.join(output,"failure.png"),fullPage:true}).catch(()=>{});
    throw error;
  } finally {
    await fs.writeFile(path.join(output,"report.json"),JSON.stringify(report,null,2));
    console.log(`PLECS_E2E_REPORT ${output}`);
  }
});
