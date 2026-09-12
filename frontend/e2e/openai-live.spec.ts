import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import type { Workspace, WorkspaceJob } from "../src/lib/workspace";

test.describe.configure({retries: 0});

test("OpenAI live: PDF analysis, grounded proposal, comparison and review downloads", async ({page}) => {
  test.skip(process.env.E2E_OPENAI_LIVE !== "true", "Explicit paid OpenAI opt-in only");
  test.setTimeout(600_000);
  page.setDefaultTimeout(20_000);
  const no = process.env.E2E_OPENAI_NOTICE || "";
  expect(no).toMatch(/^E2E-OPENAI-[A-Za-z0-9-]+$/);
  const root = path.resolve(process.cwd(), "..");
  const samples = path.join(root, "output/pdf/document-loop-samples");
  const output = path.join(root, "data/workspace/openai-live", no);
  await fs.mkdir(output, {recursive:true});
  const resume = process.env.E2E_OPENAI_RESUME === "true";
  const report: {notice_no:string; steps:string[]; jobs:unknown[]; errors:string[]; artifacts:unknown[]; final?:unknown} = {
    notice_no:no, steps:[], jobs:[], errors:[], artifacts:[],
  };
  if (resume) {
    Object.assign(report, JSON.parse(await fs.readFile(path.join(output,"result.json"),"utf8")));
    expect(report.final, "A completed scenario must not be resumed").toBeUndefined();
  }
  const status = page.getByRole("status", {name:"실행 결과"});
  const prefix = `/api/v2/notices/${no}`;
  const current = async (): Promise<Workspace> => {
    const response = await page.request.get(`${prefix}/workspace`);
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const waitJob = async (kind:string, id?:string): Promise<WorkspaceJob> => {
    let job: WorkspaceJob | undefined;
    await expect.poll(async () => {
      job = (await current()).jobs.find(item => id ? item.id === id : item.kind === kind);
      return job && !["queued", "running"].includes(job.status);
    }, {timeout:220_000, intervals:[1000, 2000, 3000]}).toBeTruthy();
    report.jobs.push({id:job!.id, kind, status:job!.status, error:job!.error, result:job!.result});
    expect(job!.status, JSON.stringify(job!.error)).toBe("succeeded");
    return job!;
  };
  const apply = async (label:string) => {
    const article = page.locator("article").filter({has:page.getByText(`${label} · 완료`, {exact:true})}).first();
    await article.getByRole("button", {name:"결과 반영", exact:true}).click({timeout:30000});
    await expect(status).toContainText("검토 대상으로 반영 완료");
  };
  try {
    await page.goto("/workspace");
    const config = await page.request.get("/api/v2/settings");
    expect(config.ok()).toBeTruthy();
    const selected = (await config.json()).llm;
    expect(selected.provider).toBe("openai");
    expect(selected.key_registered).toBe(true);
    let state: Workspace;
    if (!resume) {
    const exists = await page.request.get(`${prefix}/workspace`);
    expect(exists.status(), "Never restart a paid scenario under the same notice automatically").toBe(404);
    await page.getByText("공고 수동 등록", {exact:true}).click();
    await page.getByLabel("공고번호", {exact:true}).fill(no);
    await page.getByLabel("공고명", {exact:true}).fill("[TEST ONLY] OpenAI 실제 호출 서류 작성 검증");
    await page.getByRole("button", {name:"등록", exact:true}).click();
    await expect(page.getByText("공고 등록 완료", {exact:true})).toBeVisible();
    await page.getByLabel("공고 검색", {exact:true}).fill(no);
    await page.getByRole("button", {name:"공고 검색 실행", exact:true}).click();
    await page.locator(`a[href="/workspace/${no}"]`).click();
    await page.getByRole("button", {name:"검토 시작", exact:true}).click();
    await page.getByLabel("검토 의견", {exact:true}).fill("[TEST ONLY] 가상 원문·근거 검증이며 실제 입찰 승인 아님.");
    for (const [file, role] of [["01-sample-notice.pdf", "notice_source"], ["03-sample-product-evidence.pdf", "product_evidence"]]) {
      await page.getByRole("combobox", {name:"문서 구분", exact:true}).selectOption(role);
      await page.getByLabel("파일", {exact:true}).setInputFiles(path.join(samples,file));
      await page.getByRole("button", {name:"등록", exact:true}).click();
      await expect(status).toContainText("파일 등록 완료");
    }
    await page.getByRole("tab", {name:"3. 비교·작성", exact:true}).click();
    await page.getByLabel("회사 기존 작성자료", {exact:true}).setInputFiles(path.join(samples,"02-previous-proposal.pdf"));
    await page.getByRole("button", {name:"작성자료 등록", exact:true}).click();
    await expect(status).toContainText("기존 작성자료 등록 완료");
    await page.getByRole("button", {name:"본문 추출", exact:true}).click();
    await waitJob("extract");
    await apply("본문 추출");
    state = await current();
    expect(state.inputs.documents).toHaveLength(3);
    for (const document of state.inputs.documents) expect(document.text).toContain("TEST ONLY");
    report.steps.push("독립 가상 공고 등록·검색, PDF 3개 업로드 및 실제 본문 추출");
    await page.getByRole("tab", {name:"2. 공고 서류 검토", exact:true}).click();
    const evidenceRow = page.getByRole("link", {name:"03-sample-product-evidence.pdf", exact:true}).locator("..").locator("..");
    await evidenceRow.getByRole("button", {name:"증빙 확인", exact:true}).click();
    await expect(status).toContainText("저장 완료");
    await page.getByRole("button", {name:"요구사항 분석", exact:true}).click();
    const analysis = await waitJob("analyze");
    expect((analysis.result as {llm_usage?:{provider:string}})?.llm_usage?.provider).toBe("openai");
    await apply("요구사항 분석");
    state = await current();
    expect(state.inputs.requirements.length).toBeGreaterThanOrEqual(3);
    const source = state.inputs.documents.find(d => d.role === "notice_source")!;
    for (const req of state.inputs.requirements) {
      expect(source.text).toContain(req.quote);
      expect(req.review_status).toBe("pending");
    }
    report.steps.push("OpenAI 실제 원문 분석 1회, 인용 검증 및 검토 대기 반영");
    } else {
      state = await current();
      expect(state.inputs.documents).toHaveLength(3);
      expect(state.inputs.documents.every(d => d.text?.includes("TEST ONLY"))).toBe(true);
      expect(state.inputs.requirements.length).toBeGreaterThanOrEqual(3);
      const prior = state.jobs.find(j => j.kind === "analyze");
      expect(prior?.status).toBe("succeeded");
      expect((prior?.result as {llm_usage?:{provider:string}})?.llm_usage?.provider).toBe("openai");
      const generated = state.jobs.filter(j => j.kind === "proposal");
      expect(generated.length).toBeLessThanOrEqual(1);
      if (generated.length) {
        expect(generated[0].status, "Never retry a failed paid proposal").toBe("succeeded");
        expect((generated[0].result as {llm_usage?:{provider:string}})?.llm_usage?.provider).toBe("openai");
        expect(state.inputs.proposal_sections?.length, "Resume only after result was applied").toBeGreaterThan(0);
      }
      await page.goto(`/workspace/${no}#writing`);
      report.steps.push("동일 공고에서 재개: 기존 성공 분석·제안서 재호출 없음");
    }

    // The simplified UI exposes comparison writing, not paid proposal generation.
    // This explicit opt-in API action is the only second paid generation request.
    await page.getByRole("tab", {name:"3. 비교·작성", exact:true}).click();
    await page.getByLabel("검토 의견", {exact:true}).fill("[TEST ONLY] 가상 자료 비교 및 다운로드 검증. 실제 입찰 승인 아님.");
    if (!state.jobs.some(j => j.kind === "proposal")) {
    const response = await page.request.post(`${prefix}/jobs`, {headers:{Origin:new URL(page.url()).origin}, data:{
      kind:"proposal", input_version:state.version, idempotency_key:`${no}-proposal`, template_key:"proposal",
    }});
    expect(response.ok(), `Proposal request HTTP ${response.status()}`).toBeTruthy();
    const proposal = await waitJob("proposal", (await response.json()).id);
    expect((proposal.result as {llm_usage?:{provider:string}})?.llm_usage?.provider).toBe("openai");
    await page.getByRole("button", {name:"최신 상태", exact:true}).click();
    await apply("검토 초안");
    state = await current();
    expect(state.inputs.proposal_sections?.length).toBeGreaterThan(0);
    expect(state.inputs.proposal_sections?.every(s => s.review_status === "pending")).toBe(true);
    expect(state.inputs.documents.find(d => d.role === "company_reference")?.confirmed).toBe(false);
    report.steps.push("OpenAI 실제 제안서 생성 API 1회, 근거 연결 및 자동 승인 금지 확인");
    }

    const requirement = state.inputs.requirements.find(r => r.quote.includes("3대"))!;
    expect(requirement).toBeTruthy();
    await page.getByRole("combobox", {name:"이번 공고 요구사항", exact:true}).selectOption(requirement.id);
    await page.getByLabel("참고할 원문 인용", {exact:true}).fill("이전 사업에서는 교육용 시뮬레이터 장비 2대를 제안했습니다.");
    await page.getByLabel("이번 공고에 맞춘 작성 내용", {exact:true}).fill("[TEST ONLY] 교육용 시뮬레이터 장비 3대를 제안합니다. [검증필요]");
    await page.getByRole("button", {name:"비교 작성 초안 저장", exact:true}).click();
    await expect(status).toContainText("비교 작성 초안 저장 완료");
    report.steps.push("이전 2대와 신규 3대 조건 비교, 수정 초안을 검토 대기로 저장");
    await page.getByRole("tab", {name:"4. 서류 확인", exact:true}).click();
    await expect(page.getByLabel("제안서 섹션 본문", {exact:true}).first()).toBeVisible();
    await page.getByRole("button", {name:"누락 검사", exact:true}).click();
    await waitJob("verify");
    for (const [button, kind, filename] of [["Excel 생성","excel","requirements.xlsx"], ["검토 패키지","package","review-package.zip"]]) {
      await page.getByRole("button", {name:button, exact:true}).click();
      const job = await waitJob(kind);
      const article = page.locator("article").filter({has:page.getByText(`${button} · 완료`, {exact:true})}).first();
      const download = page.waitForEvent("download");
      await article.getByRole("link", {name:"다운로드", exact:true}).click();
      await (await download).saveAs(path.join(output,filename));
      const bytes = await fs.readFile(path.join(output,filename));
      const digest = createHash("sha256").update(bytes).digest("hex");
      expect(digest).toBe((job.result as {sha256?:string})?.sha256);
      report.artifacts.push({kind, job_id:job.id, bytes:bytes.length, sha256:digest, filename});
    }
    report.steps.push("누락 검사 및 Excel·패키지 실제 다운로드, 해시 일치 확인");
    await page.getByRole("button", {name:"필수조건 다시 확인", exact:true}).click();
    await expect(page.getByRole("status", {name:"필수조건 결과"})).toContainText("HWP 생성 전 보완 필요");
    await page.getByRole("button", {name:"입력값 확인", exact:true}).click();
    await expect(page.getByRole("button", {name:"HWP 생성", exact:true})).toBeDisabled();
    state = await current();
    expect(state.ready).toBe(false);
    expect(state.inputs.proposal_sections?.every(s => s.review_status === "pending")).toBe(true);
    report.final = {version:state.version, ready:state.ready, requirements:state.inputs.requirements.length, sections:state.inputs.proposal_sections?.length, blockers:state.blockers};
    await page.screenshot({path:path.join(output,"review-desktop.png"),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:path.join(output,"review-mobile.png"),fullPage:true});
    report.steps.push("검토 대기·HWP 차단·모바일 가로 넘침 없음 확인; 실제 제출 없음");
  } catch (error) {
    report.errors.push(String(error));
    await page.screenshot({path:path.join(output,"failure.png"),fullPage:true}).catch(() => {});
    throw error;
  } finally {
    await fs.writeFile(path.join(output,"result.json"),JSON.stringify(report,null,2));
    console.log(`OPENAI_LIVE_REPORT ${no} ${output}`);
  }
});
