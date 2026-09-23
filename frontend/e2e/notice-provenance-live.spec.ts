import {expect, test} from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {createHash, randomUUID} from "node:crypto";
import {testPdf, zipEntries} from "./fixtures/attachmentOnly";
import {fictionalHwpx, testZip} from "./fixtures/noticeProvenance";
import type {Workspace, WorkspaceJob} from "../src/lib/workspace";

test("TEST ONLY: ZIP HWPX citation, save, reopen, download and package provenance", async ({page, request}) => {
  test.skip(process.env.E2E_WORKSPACE_V2 !== "true" || process.env.E2E_NOTICE_PROVENANCE !== "true", "synthetic local rehearsal only");
  test.setTimeout(240_000);
  page.setDefaultTimeout(15_000);
  const api = process.env.E2E_API_BASE || "http://127.0.0.1:8002";
  const noticeNo = `E2E-PROVENANCE-${Date.now()}`, prefix = `${api}/v2/notices/${noticeNo}`;
  const output = path.resolve("../data/workspace/provenance-loop", noticeNo);
  await fs.mkdir(output, {recursive: true});
  const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");
  const original = testZip({"forms/proposal.hwpx": fictionalHwpx()});
  const quote = "TEST ONLY: fictional reference content for document writing.";
  const post = async (url: string, data: unknown) => {
    const response = await request.post(url, {data});
    expect(response.ok(), await response.text()).toBeTruthy(); return response.json();
  };
  const current = async (): Promise<Workspace> => (await request.get(`${prefix}/workspace`)).json();
  const run = async (kind: string): Promise<WorkspaceJob> => {
    const state = await current();
    const job = await post(`${prefix}/jobs`, {kind, input_version: state.version, idempotency_key: randomUUID()});
    await expect.poll(async () => (await current()).jobs.find(j => j.id === job.id)?.status, {timeout: 90_000}).toMatch(/succeeded|failed|blocked|uncertain/);
    const done = (await current()).jobs.find(j => j.id === job.id)!;
    expect(done.status, JSON.stringify(done.error)).toBe("succeeded"); return done;
  };
  await post(`${api}/v2/notices`, {notice_no: noticeNo, title: "[TEST ONLY] ZIP 양식 출처 검증", source: "MANUAL_E2E", raw: {bidClseDt: "2027-01-20 10:00:00"}});
  let ws: Workspace = await post(`${prefix}/initialize`, {});
  for (const file of [{name: "fictional.zip", type: "application/zip", role: "notice_source", bytes: original},
    {name: "fictional-reference.pdf", type: "application/pdf", role: "company_reference", bytes: testPdf([quote])}]) {
    const response = await request.post(`${prefix}/documents`, {multipart: {version: ws.version, role: file.role, file: {name: file.name, mimeType: file.type, buffer: file.bytes}}});
    expect(response.ok(), await response.text()).toBeTruthy(); ws = await response.json();
  }
  const extract = await run("extract");
  ws = await post(`${prefix}/jobs/${extract.id}/apply`, {version: ws.version});
  const reference = ws.inputs.documents.find(d => d.role === "company_reference")!;
  const source = ws.inputs.documents.find(d => d.role === "notice_source")!;
  expect(reference.text).toContain(quote);
  await post(`${prefix}/requirements`, {version: ws.version, text: "TEST ONLY 납품기한 검토", document_id: source.id,
    quote: "납품 설치 기한 : 계약체결일로부터 120일 이내", locator: "forms/proposal.hwpx 납품기한", category: "schedule", review_status: "pending", compliance: "unassessed"});
  await page.goto(`/workspace/${noticeNo}`);
  await expect(page.getByRole("region", {name: "공고 핵심 사항"})).toContainText("260,000,000원");
  await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
  const form = page.getByRole("region", {name: "공고 첨부 양식 작성"});
  await expect(form).toContainText("내부 파일: forms/proposal.hwpx");
  await form.getByLabel("양식 항목 작성 내용", {exact: true}).fill(quote);
  await form.getByRole("combobox", {name: "참고자료 종류", exact: true}).selectOption("company");
  await form.getByRole("combobox", {name: "참고할 회사 자료", exact: true}).selectOption(reference.id);
  await form.getByLabel("자료에서 발췌한 근거", {exact: true}).fill(quote);
  await form.getByRole("button", {name: "양식 초안 저장", exact: true}).click();
  await expect(form.getByRole("status").filter({hasText: "첨부 양식 초안 저장 완료"})).toBeVisible();
  await page.reload();
  await page.getByRole("tab", {name: "3. 비교·작성", exact: true}).click();
  await expect(form.getByLabel("양식 항목 작성 내용", {exact: true})).toHaveValue(quote);
  const download = page.waitForEvent("download");
  await form.getByRole("link", {name: "작성된 첨부 양식 다운로드 (HWPX)", exact: true}).click();
  const filledPath = path.join(output, "review-copy.hwpx");
  await (await download).saveAs(filledPath);
  const filled = await fs.readFile(filledPath);
  expect(zipEntries(filled).get("Contents/section0.xml")!.toString()).toContain(quote);
  const downloadedOriginal = await (await request.get(`${prefix}/documents/${source.id}/download`)).body();
  expect(sha(downloadedOriginal)).toBe(sha(original));
  await run("verify"); await run("excel");
  const packaged = await run("package");
  const pkg = await (await request.get(`${api}/v2/jobs/${packaged.id}/download`)).body();
  expect(sha(pkg)).toBe(packaged.result?.sha256);
  await fs.writeFile(path.join(output, "review-package.zip"), pkg);
  const entries = zipEntries(pkg), manifest = JSON.parse(entries.get("manifest.json")!.toString());
  const file = manifest.files.find((f: {name?: string}) => f.name?.startsWith("forms/"));
  expect(file.original_form.container_sha256).toBe(sha(original));
  expect(file.original_form.member_path).toEqual(["forms/proposal.hwpx"]);
  expect(sha(entries.get(file.name)!)).toBe(sha(filled));
  ws = await current();
  expect(ws.inputs.documents).toHaveLength(2);
  expect(ws.inputs.documents.find(d => d.id === reference.id)?.confirmed).toBe(false);
  expect(ws.ready).toBe(false);
  expect(ws.jobs.some(j => j.kind === "jev")).toBe(false);
  await fs.writeFile(path.join(output, "report.json"), JSON.stringify({notice_no: noticeNo, version: ws.version, original_sha256: sha(original), output_sha256: sha(filled), package_sha256: sha(pkg), ready: ws.ready, steps: ["summary", "choose ZIP HWPX", "link reference", "save", "reopen", "readback", "download", "package provenance"], layout_verified: false}, null, 2));
});
