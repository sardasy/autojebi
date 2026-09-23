import {expect, test, type Locator} from "@playwright/test";
import {createHash} from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import type {Workspace, WorkspaceJob} from "../src/lib/workspace";
import {testPdf, zipEntries} from "./fixtures/attachmentOnly";

test("TEST ONLY: attachment and electronic submission plan reaches reviewed Excel/ZIP readiness", async ({page, request}, testInfo) => {
  test.skip(process.env.E2E_WORKSPACE_V2 !== "true" || process.env.E2E_ATTACHMENT_ONLY !== "true", "explicit synthetic live rehearsal only");
  test.setTimeout(360_000);
  page.setDefaultTimeout(15_000);
  const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
  const noticeNo = `E2E-ATTACHMENT-ONLY-${Date.now()}`;
  const output = path.resolve(process.cwd(), "../data/workspace/attachment-only-loop", noticeNo);
  await fs.mkdir(output, {recursive: true});
  const sourceName = "test-only-attachment-notice.pdf", evidenceName = "test-only-registration.pdf";
  const sourceQuote = "Certificate of registration must be attached as the original file.";
  const electronicQuote = "Price bid is submitted electronically by the responsible operator.";
  const proof = "TEST ONLY: fictional registration is current.";
  const sourceBytes = testPdf(["TEST ONLY - FICTIONAL NOTICE - DO NOT SUBMIT", "Submission requirements:", sourceQuote, electronicQuote]);
  const evidenceBytes = testPdf(["TEST ONLY - FICTIONAL EVIDENCE - NOT A REAL CERTIFICATE", proof]);
  const report: {notice_no: string; steps: string[]; error?: string; state?: unknown} = {notice_no: noticeNo, steps: []};
  const status = page.getByRole("status", {name: "실행 결과"});
  const current = async (): Promise<Workspace> => {
    const response = await request.get(`${api}/v2/notices/${noticeNo}/workspace`);
    expect(response.ok()).toBeTruthy(); return response.json();
  };
  const reveal = async (target: Locator) => {
    await target.waitFor({state: "attached"});
    for (let attempt = 0; attempt < 8 && !await target.isVisible(); attempt++) {
      const ancestors = await target.locator("xpath=ancestor::details[not(@open)]").all();
      let opened = false;
      for (const details of ancestors) {
        const summary = details.locator(":scope > summary");
        if (await summary.isVisible()) {await summary.click(); opened = true; break;}
      }
      if (!opened) break;
    }
    await expect(target).toBeVisible();
  };
  const completed = async (kind: string): Promise<WorkspaceJob> => {
    await expect.poll(async () => (await current()).jobs.find(job => job.kind === kind)?.status,
      {timeout: 90_000}).toBe("succeeded");
    return (await current()).jobs.find(job => job.kind === kind)!;
  };
  const download = async (article: Locator, job: WorkspaceJob, filename: string) => {
    await reveal(article);
    const started = page.waitForEvent("download");
    await article.getByRole("link", {name: "다운로드", exact: true}).click();
    await (await started).saveAs(path.join(output, filename));
    const bytes = await fs.readFile(path.join(output, filename));
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(job.result?.sha256);
    return bytes;
  };
  try {
    await page.goto("/workspace");
    await page.getByText("공고 수동 등록", {exact: true}).click();
    await page.getByLabel("공고번호", {exact: true}).fill(noticeNo);
    await page.getByLabel("공고명", {exact: true}).fill("[TEST ONLY] 원본 첨부와 전자 제출 완료 검증");
    await page.getByLabel("공고 기관", {exact: true}).fill("가상 시험 기관");
    await page.getByLabel("입찰 마감일시 (한국시간)", {exact: true}).fill(`${new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)}T14:00`);
    await page.getByRole("button", {name: "등록", exact: true}).click();
    await expect(page.getByText("공고 등록 완료", {exact: true})).toBeVisible();
    await page.getByLabel("공고 검색", {exact: true}).fill(noticeNo);
    await page.getByRole("button", {name: "공고 검색 실행", exact: true}).click();
    await page.locator(`a[href="/workspace/${noticeNo}"]`).click();
    await page.getByRole("button", {name: "검토 시작", exact: true}).click();
    await reveal(page.getByLabel("검토 의견", {exact: true}));
    await page.getByLabel("검토 의견", {exact: true}).fill("TEST ONLY 가상 원문 검증. 실제 입찰 승인 아님.");
    for (const file of [{name: sourceName, role: "notice_source", buffer: sourceBytes}, {name: evidenceName, role: "company_evidence", buffer: evidenceBytes}]) {
      await reveal(page.locator('#source-details select[name="role"]'));
      await page.getByRole("combobox", {name: "문서 구분", exact: true}).selectOption(file.role);
      await page.getByLabel("파일", {exact: true}).setInputFiles({name: file.name, mimeType: "application/pdf", buffer: file.buffer});
      await page.getByRole("button", {name: "등록", exact: true}).click();
      await expect(status).toContainText("파일 등록 완료");
    }
    await page.getByRole("region", {name: "지금 할 작업"}).getByRole("button", {name: "원문 본문 추출", exact: true}).click();
    await completed("extract");
    await page.getByRole("region", {name: "지금 할 작업"}).getByRole("button", {name: "추출한 본문 반영", exact: true}).click();
    await expect(status).toContainText("본문 반영 완료");
    let state = await current();
    const source = state.inputs.documents.find(doc => doc.role === "notice_source")!;
    const evidence = state.inputs.documents.find(doc => doc.role === "company_evidence")!;
    expect(source.text).toContain(sourceQuote); expect(evidence.text).toContain(proof);
    report.steps.push("가상 PDF 두 개를 실제 화면으로 등록·추출·반영");

    const plan = page.getByRole("region", {name: "작성 대상 검토"});
    await plan.getByText("누락된 서류·세부 작성 항목 추가", {exact: true}).click();
    for (const item of [{title: "Certificate of registration", quote: sourceQuote, action: "attach"}, {title: "Price bid", quote: electronicQuote, action: "electronic"}]) {
      await plan.getByLabel("원문의 항목명", {exact: true}).fill(item.title);
      await plan.getByRole("combobox", {name: "근거 파일", exact: true}).selectOption(source.id);
      await plan.getByLabel("항목명이 포함된 원문 인용", {exact: true}).fill(item.quote);
      await plan.getByRole("button", {name: "항목 추가", exact: true}).click();
      await plan.getByRole("combobox", {name: `${item.title} 처리`, exact: true}).selectOption(item.action);
    }
    await plan.getByLabel("공고 서류를 검토하고 작성·첨부 대상을 확인했습니다.").check();
    await plan.getByRole("button", {name: "확인 완료 · 비교·작성으로 이동", exact: true}).click();
    await expect(page.getByText("확인한 목록에 직접 작성할 항목이 없습니다.")).toBeVisible();
    await page.getByRole("tab", {name: "2. 공고 서류 검토", exact: true}).click();
    state = await current();
    const attachment = state.inputs.writing_plan!.items.find(item => item.action === "attach")!;
    const evidenceRow = page.getByRole("link", {name: evidenceName, exact: true, includeHidden: true}).locator("..").locator("..");
    await reveal(evidenceRow.getByRole("button", {name: "증빙 확인", exact: true, includeHidden: true}));
    await evidenceRow.getByRole("combobox", {name: `${evidenceName} 연결 서류`, exact: true}).selectOption(attachment.id);
    await evidenceRow.getByRole("button", {name: "증빙 확인", exact: true}).click();
    await expect(status).toHaveText("저장 완료");
    const add = page.locator("#source-requirement-entry");
    await reveal(add.locator(":scope > summary"));
    if (await add.getAttribute("open") === null) await add.locator(":scope > summary").click();
    const form = add.locator("form");
    await form.getByLabel("요구사항", {exact: true}).fill("TEST ONLY 등록증 원본 제출");
    await form.getByRole("combobox", {name: "공고 원문", exact: true}).selectOption(source.id);
    await form.getByLabel("원문 인용", {exact: true}).fill(sourceQuote);
    await form.getByLabel("원문 페이지·문단", {exact: true}).fill("1페이지 Submission requirements");
    await form.getByRole("combobox", {name: "유형", exact: true}).selectOption("qualification");
    await form.getByLabel("제안값", {exact: true}).fill("TEST ONLY 가상 등록증 원본 첨부");
    await form.getByRole("combobox", {name: "확인된 근거", exact: true}).selectOption(evidence.id);
    await form.getByLabel("근거 인용", {exact: true}).fill(proof);
    await form.getByLabel("근거 페이지·문단", {exact: true}).fill("1페이지 가상 등록 상태");
    await form.getByRole("combobox", {name: "제안서 반영", exact: true}).selectOption("evidence_only");
    await form.getByLabel("별도 증빙 충족 사유", {exact: true}).fill("공고에서 원본 첨부만 요구함. 실제 기관 자격을 뜻하지 않는 가상 검증.");
    await form.getByRole("combobox", {name: "담당자 충족 판정", exact: true}).selectOption("meets");
    await form.getByRole("combobox", {name: "검토 상태", exact: true}).selectOption("accepted");
    await form.getByRole("button", {name: "저장", exact: true}).click();
    await expect(status).toHaveText("저장 완료");
    const sourceReview = page.getByRole("button", {name: "원문 전체 대조 확인", exact: true, includeHidden: true});
    await reveal(sourceReview); await sourceReview.click();
    await expect(status).toContainText("원문 대조 확인 저장");
    report.steps.push("첨부·전자 제출 계획, 원본 증빙 연결, evidence_only 요구사항·원문 대조 확인");

    await page.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
    await reveal(page.getByRole("combobox", {name: "참가 결정", exact: true, includeHidden: true}));
    await page.getByRole("combobox", {name: "참가 결정", exact: true}).selectOption("participate");
    await page.getByLabel("참가 결정 의견", {exact: true}).fill("TEST ONLY 가상 참가 상태 검증");
    await page.getByRole("button", {name: "참가 결정 저장", exact: true}).click();
    await expect.poll(async () => (await current()).decision).toBe("participate");
    const outputPlan = page.getByRole("form", {name: "출력 서류 계획", includeHidden: true});
    await reveal(outputPlan);
    await outputPlan.getByRole("checkbox", {name: /HWP 생성 불필요/}).check();
    await outputPlan.getByLabel("출력 서류 확인 의견").fill("TEST ONLY 확인한 제출 방식은 원본 첨부·전자 제출뿐임");
    await outputPlan.getByRole("button", {name: "출력 서류 계획 저장"}).click();
    await expect.poll(async () => (await current()).inputs.output_plan?.template_keys).toEqual([]);
    await expect(page.getByRole("button", {name: "HWP 생성", exact: true})).toHaveCount(0);
    await page.getByRole("button", {name: "누락 검사", exact: true}).click();
    await completed("verify");
    expect((await current()).blockers).toEqual([]);
    await page.getByRole("button", {name: "Excel 생성", exact: true}).click();
    const excel = await completed("excel");
    const excelArticle = page.locator("article").filter({has: page.getByText("Excel 생성 · 완료", {exact: true})}).first();
    const workbook = zipEntries(await download(excelArticle, excel, "requirements.xlsx"));
    expect(workbook.get("xl/worksheets/sheet1.xml")?.toString()).toContain(sourceQuote);
    expect(workbook.get("xl/worksheets/sheet1.xml")?.toString()).toContain(proof);
    await excelArticle.getByLabel("파일 검토 의견", {exact: true}).fill("TEST ONLY 내려받은 Excel의 원문·증빙 인용 일치 확인");
    await excelArticle.getByRole("button", {name: "초안 승인", exact: true}).click();
    await expect(excelArticle.getByText("검토 상태: 승인", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "검토 패키지", exact: true}).click();
    const packageJob = await completed("package");
    expect(packageJob.result?.warnings).toEqual([]);
    const packageArticle = page.locator("article").filter({has: page.getByText("검토 패키지 · 완료", {exact: true})}).first();
    const packagedBytes = await download(packageArticle, packageJob, "review-package.zip");
    const archive = zipEntries(packagedBytes);
    const manifest = JSON.parse(archive.get("manifest.json")!.toString());
    expect(manifest.inputs.output_plan.template_keys).toEqual([]);
    expect(archive.get(`sources/${source.id}.pdf`)).toEqual(sourceBytes);
    expect(archive.get(`sources/${evidence.id}.pdf`)).toEqual(evidenceBytes);
    expect(archive.has(`outputs/${excel.id}.xlsx`)).toBe(true);
    expect(archive.has("proposal.txt")).toBe(false);
    expect(archive.get("missing.txt")?.toString()).toBe("");
    await packageArticle.getByLabel("파일 검토 의견", {exact: true}).fill("TEST ONLY 원본·Excel·누락목록 대조 완료. 실제 공고 제출 승인 아님.");
    await packageArticle.getByRole("button", {name: "제출 준비 확인", exact: true}).click();
    await expect.poll(async () => (await current()).ready).toBe(true);
    state = await current();
    expect(state.jobs.some(job => ["hwp", "hwp_inspect"].includes(job.kind))).toBe(false);
    report.steps.push("HWP 생략 명시 → 실제 Excel 인용·ZIP 원본 대조 → TEST ONLY ready=true");
    report.state = {version: state.version, ready: state.ready, blockers: state.blockers, output_plan: state.inputs.output_plan};
    await page.screenshot({path: path.join(output, "review-ready.png"), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path: path.join(output, "review-mobile.png"), fullPage: true});
    await page.setViewportSize({width: 1280, height: 800});
    await page.getByRole("tab", {name: "2. 공고 서류 검토", exact: true}).click();
    await reveal(page.getByLabel("검토 의견", {exact: true}));
    await page.getByLabel("검토 의견", {exact: true}).fill("TEST ONLY 최종 검토 이후 증빙의 실제 변경에 따른 무효화 검증");
    const evidenceText = evidenceRow.getByLabel(`${evidenceName} 본문`, {exact: true});
    await reveal(evidenceText);
    await evidenceText.fill(`${evidence.text}\nTEST ONLY: evidence revised after final review.`);
    await evidenceRow.getByRole("button", {name: "확인된 본문 저장", exact: true}).click();
    await expect(status).toHaveText("저장 완료");
    const changed = await current();
    expect(changed.version).toBe(state.version + 1);
    expect(changed.ready).toBe(false);
    expect(changed.inputs.requirements[0].review_status).toBe("pending");
    expect(changed.jobs.find(job => job.id === packageJob.id)?.result?.sha256).toBe(packageJob.result?.sha256);
    await page.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
    expect(await download(packageArticle, packageJob, "previous-review-package.zip")).toEqual(packagedBytes);
    await expect(packageArticle.getByRole("button", {name: "제출 준비 확인", exact: true})).toBeDisabled();
    await page.screenshot({path: path.join(output, "review-invalidated.png"), fullPage: true});
    report.steps.push("화면에서 증빙 본문 실제 변경 → 새 버전·ready=false·요구사항 재검토 → 과거 ZIP 동일 바이트 보존");
    report.state = {completed: report.state, after_evidence_change: {version: changed.version, ready: changed.ready, blockers: changed.blockers}};
  } catch (error) {
    report.error = String(error);
    await page.screenshot({path: path.join(output, "failure.png"), fullPage: true}).catch(() => {});
    throw error;
  } finally {
    const reportPath = path.join(output, "result.json");
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    await testInfo.attach("attachment-only-rehearsal", {path: reportPath, contentType: "application/json"});
  }
});
