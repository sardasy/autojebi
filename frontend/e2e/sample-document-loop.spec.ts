import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

test("sample PDFs: extract, compare, revise, verify and download", async ({page, request}) => {
  test.skip(process.env.E2E_WORKSPACE_V2 !== "true" || process.env.E2E_SAMPLES !== "true", "explicit sample rehearsal only");
  test.setTimeout(240_000);
  page.setDefaultTimeout(15000);
  const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
  const no = `E2E-SAMPLES-${Date.now()}`;
  const root = path.resolve(process.cwd(), "..");
  const samples = path.join(root, "output/pdf/document-loop-samples");
  const output = path.join(root, "data/workspace/sample-loop", no);
  await fs.mkdir(output, {recursive: true});
  const report: {notice_no: string; url: string; steps: string[]; findings: string[]; error?: string; state?: unknown} = {
    notice_no: no, url: `http://127.0.0.1:3002/workspace/${no}#review`, steps: [], findings: [],
  };
  const status = page.getByRole("status", {name: "실행 결과"});
  const current = async () => {
    const response = await request.get(`${api}/v2/notices/${no}/workspace`);
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const requirements = [
    {name: "공급 수량", quote: "교육용 시뮬레이터 장비 3대를 공급해야 합니다.", old: "이전 사업에서는 교육용 시뮬레이터 장비 2대를 제안했습니다.", proof: "교육용 시뮬레이터 장비 3대 공급을 가정합니다.", value: "장비 3대", draft: "[가상 테스트] 이번 공고에는 교육용 시뮬레이터 장비 3대를 제안합니다."},
    {name: "납품 기한", quote: "계약일로부터 30일 이내에 납품해야 합니다.", old: "이전 사업의 납품 기한은 계약일로부터 60일입니다.", proof: "계약일로부터 30일 이내 납품을 가정합니다.", value: "계약일로부터 30일", draft: "[가상 테스트] 이번 공고의 납품 기한은 계약일로부터 30일입니다."},
    {name: "보증기간", quote: "검수 완료일로부터 24개월의 보증을 제공해야 합니다.", old: "이전 사업의 보증기간은 검수 완료일로부터 12개월입니다.", proof: "검수 완료일로부터 24개월 보증을 가정합니다.", value: "검수 완료일로부터 24개월", draft: "[가상 테스트] 검수 완료일로부터 24개월의 보증을 제안합니다."},
  ];
  try {
    await page.goto("/workspace");
    await page.getByText("공고 수동 등록", {exact: true}).click();
    await page.getByLabel("공고번호", {exact: true}).fill(no);
    await page.getByLabel("공고명", {exact: true}).fill("[TEST ONLY] 예시 시뮬레이터 서류 작성 실습");
    await page.getByRole("button", {name: "등록", exact: true}).click();
    await expect(page.getByText("공고 등록 완료", {exact: true})).toBeVisible();
    await page.getByLabel("공고 검색", {exact: true}).fill(no);
    await page.getByRole("button", {name: "공고 검색 실행", exact: true}).click();
    await page.locator(`a[href="/workspace/${no}"]`).click();
    await expect(page).toHaveURL(new RegExp(`/workspace/${no}$`));
    await page.getByRole("button", {name: "검토 시작", exact: true}).click();
    await page.getByLabel("검토 의견", {exact: true}).fill("가상 예시 자료의 E2E 검증입니다. 실제 입찰 승인 아님.");
    report.steps.push("예시 공고 등록 및 저장 공고 검색으로 상세 진입");

    for (const [file, role] of [["01-sample-notice.pdf", "notice_source"], ["03-sample-product-evidence.pdf", "product_evidence"]]) {
      await page.getByRole("combobox", {name: "문서 구분", exact: true}).selectOption(role);
      await page.getByLabel("파일", {exact: true}).setInputFiles(path.join(samples, file));
      await page.getByRole("button", {name: "등록", exact: true}).click();
      await expect(status).toContainText("파일 등록 완료");
    }
    await page.getByRole("button", {name: "본문 추출", exact: true}).click();
    await page.getByRole("button", {name: "결과 반영", exact: true}).click({timeout: 60000});
    await expect(status).toContainText("검토 대상으로 반영 완료");
    let state = await current();
    const source = state.inputs.documents.find((d: {role: string}) => d.role === "notice_source");
    const evidence = state.inputs.documents.find((d: {role: string}) => d.role === "product_evidence");
    for (const req of requirements) {
      expect(source.text).toContain(req.quote);
      expect(evidence.text).toContain(req.proof);
    }
    expect(evidence.confirmed).toBe(false);
    const evidenceRow = page.getByRole("link", {name: "03-sample-product-evidence.pdf", exact: true}).locator("..").locator("..");
    await evidenceRow.getByRole("button", {name: "증빙 확인", exact: true}).click();
    await expect(status).toHaveText("저장 완료");
    report.steps.push("예시 공고·제품 근거 PDF 업로드, 실제 큐 본문 추출 및 가상 근거 확인");

    for (const req of requirements) {
      await page.getByText("요구사항 추가", {exact: true}).click();
      const form = page.locator("form").filter({has: page.getByLabel("요구사항", {exact: true})}).last();
      await form.getByLabel("요구사항", {exact: true}).fill(req.name);
      await form.getByRole("combobox", {name: "공고 원문", exact: true}).selectOption(source.id);
      await form.getByLabel("원문 인용", {exact: true}).fill(req.quote);
      await form.getByLabel("원문 페이지·문단", {exact: true}).fill("1페이지, 2. 필수 요구사항");
      await form.getByLabel("제안값", {exact: true}).fill(req.value);
      await form.getByRole("combobox", {name: "확인된 근거", exact: true}).selectOption(evidence.id);
      await form.getByLabel("근거 인용", {exact: true}).fill(req.proof);
      await form.getByLabel("근거 페이지·문단", {exact: true}).fill("1페이지, 2. 검증용 공급조건 (가상)");
      await form.getByRole("combobox", {name: "담당자 충족 판정", exact: true}).selectOption("meets");
      await form.getByRole("combobox", {name: "검토 상태", exact: true}).selectOption("accepted");
      await form.getByRole("button", {name: "저장", exact: true}).click();
      await expect(status).toHaveText("저장 완료");
      if (await form.isVisible()) await page.getByText("요구사항 추가", {exact: true}).click();
    }
    await page.getByRole("button", {name: "원문 전체 대조 확인", exact: true}).click();
    await expect(status).toContainText("원문 대조 확인 저장");
    report.steps.push("3개 요구사항을 원문 인용·가상 근거·제안값과 연결하여 검토");

    await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
    await page.getByLabel("회사 기존 작성자료", {exact: true}).setInputFiles(path.join(samples, "02-previous-proposal.pdf"));
    await page.getByRole("button", {name: "작성자료 등록", exact: true}).click();
    await expect(status).toContainText("기존 작성자료 등록 완료");
    await page.getByRole("button", {name: "본문 추출", exact: true}).click();
    await page.getByRole("button", {name: "결과 반영", exact: true}).click({timeout: 60000});
    await expect(status).toContainText("검토 대상으로 반영 완료");
    state = await current();
    const previous = state.inputs.documents.find((d: {role: string}) => d.role === "company_reference");
    expect(previous.confirmed).toBe(false);
    for (const req of requirements) expect(previous.text).toContain(req.old);
    report.steps.push("이전 제안서 PDF 실제 추출, 2대·60일·12개월의 과거 조건 확인");

    for (const req of requirements) {
      const target = state.inputs.requirements.find((r: {text: string}) => r.text === req.name);
      await page.getByRole("combobox", {name: "이번 공고 요구사항", exact: true}).selectOption(target.id);
      await page.getByLabel("참고할 원문 인용", {exact: true}).fill(req.old);
      await page.getByLabel("이번 공고에 맞춘 작성 내용", {exact: true}).fill(`${req.draft} [검증필요]`);
      await page.getByRole("button", {name: "비교 작성 초안 저장", exact: true}).click();
      await expect(status).toContainText("비교 작성 초안 저장 완료");
    }
    report.steps.push("과거 조건을 새 공고의 3대·30일·24개월로 수정한 초안 3개 저장");
    await page.getByRole("tab", {name: "4. 서류 확인", exact: true}).click();
    await page.reload();
    await page.getByLabel("검토 의견", {exact: true}).fill("가상 예시 원문 대조. 실제 제출 승인 아님.");
    await expect(page.getByLabel("제안서 섹션 본문", {exact: true})).toHaveCount(3);
    const first = page.locator("form").filter({has: page.getByLabel("제안서 섹션 본문", {exact: true})}).first();
    await first.getByRole("button", {name: "내용 승인", exact: true}).click();
    await expect(status).toContainText("근거");
    expect((await current()).inputs.proposal_sections[0].review_status).toBe("pending");
    report.steps.push("검증필요 초안의 근거 없는 승인 차단");

    state = await current();
    expect(state.inputs.requirements.every((r: {review_status: string; compliance: string}) => r.review_status === "accepted" && r.compliance === "meets")).toBe(true);
    expect(state.inputs.documents.find((d: {role: string}) => d.role === "product_evidence").confirmed).toBe(true);
    expect(state.inputs.source_reviewed).toBe(true);
    report.steps.push("이전 작성자료 추출 후 기존 증빙·요구사항 검토 유지 확인");
    for (let i = 0; i < requirements.length; i++) {
      const section = page.locator("form").filter({has: page.getByLabel("제안서 섹션 본문", {exact: true})}).nth(i);
      await section.getByLabel("제안서 섹션 본문", {exact: true}).fill(requirements[i].draft);
      await section.getByRole("group", {name: "확인된 근거 자료", exact: true}).getByRole("checkbox", {name: "03-sample-product-evidence.pdf", exact: true}).check();
      await section.getByRole("button", {name: "내용 승인", exact: true}).click();
      await expect(status).toHaveText("검토 기록 저장");
    }
    state = await current();
    expect(state.inputs.proposal_sections.every((s: {review_status: string}) => s.review_status === "approved")).toBe(true);
    report.steps.push("가상 근거와 연결된 초안 3개 승인 경로 검증 (실제 제출 승인 아님)");

    await page.getByRole("button", {name: "누락 검사", exact: true}).click();
    await expect(page.getByText("누락 검사 · 완료", {exact: true})).toBeVisible({timeout: 60000});
    for (const [button, kind, filename] of [["Excel 생성", "excel", "requirements.xlsx"], ["검토 패키지", "package", "review-package.zip"]]) {
      await page.getByRole("button", {name: button, exact: true}).click();
      const article = page.locator("article").filter({has: page.getByText(`${button} · 완료`, {exact: true})}).first();
      await expect(article).toBeVisible({timeout: 60000});
      const download = page.waitForEvent("download");
      await article.getByRole("link", {name: "다운로드", exact: true}).click();
      await (await download).saveAs(path.join(output, filename));
      if (kind === "excel") {
        await article.getByRole("button", {name: "반려", exact: true}).click();
        await expect(article.getByText("검토 상태: 반려", {exact: true})).toBeVisible();
      }
    }
    report.steps.push("누락 검사, Excel·검토 패키지 실제 다운로드, Excel 반려 저장");
    await page.getByRole("button", {name: "입력값 확인", exact: true}).click();
    const generateHwp = page.getByRole("button", {name: "HWP 생성", exact: true});
    await expect(generateHwp).toBeDisabled();
    await page.getByRole("button", {name: "템플릿 필드 검사", exact: true}).click();
    await expect(page.getByText(/템플릿 필드 검사 · (차단|실패|완료)/)).toBeVisible({timeout: 60000});
    await page.getByRole("button", {name: "필수조건 다시 확인", exact: true}).click();
    await expect(page.getByRole("status", {name: "필수조건 결과"})).toContainText(/HWP 생성 전 보완 필요|제출 준비는 별도 검토/);
    const prerequisiteResponse = await request.get(`${api}/v2/notices/${no}/prerequisites?template_key=bid_form`);
    expect(prerequisiteResponse.ok()).toBeTruthy();
    const prerequisites = await prerequisiteResponse.json();
    if (!prerequisites.hwp_request_available) {
      await expect(generateHwp).toBeDisabled();
      report.findings.push("HWP 사전조건 미충족: 생성 버튼 차단 확인. 실제 HWP 생성 통과가 아님.");
    } else {
      await expect(generateHwp).toBeEnabled();
      if (process.env.E2E_HWP_LIVE === "true") {
        await generateHwp.click();
        await expect(page.getByText(/HWP 생성 · (차단|실패|완료)/)).toBeVisible({timeout: 60000});
      } else {
        report.findings.push("HWP 생성 조건 충족, 실제 파일 생성은 E2E_HWP_LIVE 명시 실행 필요.");
      }
    }
    state = await current();
    const inspection = state.jobs.find((j: {kind: string}) => j.kind === "hwp_inspect");
    report.steps.push(`HWP 필드 검사 결과: ${inspection.status}, ${inspection.error?.code || "no error"}`);
    expect(state.ready).toBe(false);
    await page.screenshot({path: path.join(output, "review-desktop.png"), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path: path.join(output, "review-mobile.png"), fullPage: true});
    await page.getByRole("tab", {name: "2. 공고 서류 검토", exact: true}).click();
    await page.setViewportSize({width: 1280, height: 800});
    const pdfResponse = page.waitForResponse(response => response.url().includes("/preview?page="));
    await page.getByRole("button", {name: "PDF 원본", exact: true}).click();
    expect((await pdfResponse).headers()["content-type"]).toContain("image/png");
    const frame = page.getByRole("img", {name: "01-sample-notice.pdf 1페이지 원본", exact: true});
    await expect(frame).toBeVisible();
    await expect.poll(() => frame.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0);
    expect(await frame.evaluate((node: HTMLImageElement) => {
      const canvas = document.createElement("canvas"); canvas.width = 64; canvas.height = 64;
      const ctx = canvas.getContext("2d")!; ctx.drawImage(node, 0, 0, 64, 64);
      const pixels = ctx.getImageData(0, 0, 64, 64).data;
      return new Set(Array.from(pixels).filter((_, index) => index % 4 !== 3)).size;
    })).toBeGreaterThan(5);
    await frame.scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(output, "source-preview.png"), fullPage: true});
    await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
    await expect(page.getByRole("table", {name: "요구사항 비교표"})).toBeVisible();
    await page.screenshot({path: path.join(output, "comparison-desktop.png"), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path: path.join(output, "comparison-mobile.png"), fullPage: true});
    report.state = {
      version: state.version, ready: state.ready, blockers: state.blockers,
      requirements: state.inputs.requirements, sections: state.inputs.proposal_sections,
      documents: state.inputs.documents.map((d: {name: string; role: string; confirmed: boolean; text: string}) => ({name: d.name, role: d.role, confirmed: d.confirmed, text_length: d.text.length})),
      jobs: state.jobs.map((j: {kind: string; status: string; error: unknown}) => ({kind: j.kind, status: j.status, error: j.error})),
    };
  } catch (error) {
    report.error = String(error);
    await page.screenshot({path: path.join(output, "failure.png"), fullPage: true}).catch(() => {});
    throw error;
  } finally {
    await fs.writeFile(path.join(output, "result.json"), JSON.stringify(report, null, 2));
    console.log(`SAMPLE_REHEARSAL ${no} ${output}`);
  }
});
