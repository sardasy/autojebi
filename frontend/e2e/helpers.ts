import { expect, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export const API_BASE = process.env.E2E_API_BASE || "http://localhost:8001";
export const API_KEY = process.env.E2E_API_KEY || "";
export const FIXTURE_DIR = path.join(__dirname, "fixtures");
export const BUSINESS_PDF_PATH = path.join(FIXTURE_DIR, "business-registration-sample.pdf");
export const TECHNICAL_SPEC_PDF_PATH = path.join(FIXTURE_DIR, "technical-spec-sample.pdf");

export type NoticeFixture = {
  notice_no: string;
  title: string;
  source: string;
  raw: Record<string, unknown>;
};

export function apiHeaders(contentType = true): Record<string, string> {
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
  };
}

export function uniqueE2EId(prefix: string): string {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const random = Math.random().toString(36).slice(2, 8).toUpperCase();
  return `E2E-${prefix}-${stamp}-${random}`;
}

export function loadFixture(name: string): NoticeFixture {
  return JSON.parse(
    fs.readFileSync(path.join(FIXTURE_DIR, name), "utf-8"),
  ) as NoticeFixture;
}

export async function upsertNotice(
  request: APIRequestContext,
  fixture: NoticeFixture,
  overrides: Partial<NoticeFixture> = {},
): Promise<NoticeFixture> {
  const notice = { ...fixture, ...overrides };
  const response = await request.post(`${API_BASE}/notices/upsert`, {
    headers: apiHeaders(),
    data: {
      notice_no: notice.notice_no,
      title: notice.title,
      source: notice.source,
      raw: notice.raw,
    },
  });
  expect(
    response.ok(),
    `seed notice failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return notice;
}

export async function cleanupE2ENotices(request: APIRequestContext) {
  const response = await request.post(`${API_BASE}/notices/e2e/cleanup`, {
    headers: apiHeaders(),
    data: {},
  });
  if (response.status() === 403 || response.status() === 404) {
    return null;
  }
  expect(
    response.ok(),
    `E2E cleanup failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.json();
}

export async function seedAnalyzedNotice(
  request: APIRequestContext,
  fixture: NoticeFixture,
  overrides: Partial<NoticeFixture> = {},
): Promise<NoticeFixture> {
  const notice = await upsertNotice(request, fixture, overrides);
  const response = await postApi(request, `/notices/${encodeURIComponent(notice.notice_no)}/analyze`);
  expect(
    response.ok(),
    `seed analyzed notice failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return notice;
}

export async function seedDocumentAutomation(
  request: APIRequestContext,
  fixture: NoticeFixture,
  overrides: Partial<NoticeFixture> = {},
): Promise<NoticeFixture> {
  const notice = await seedAnalyzedNotice(request, fixture, overrides);
  const response = await postApi(
    request,
    `/notices/${encodeURIComponent(notice.notice_no)}/documents/analyze`,
  );
  expect(
    response.ok(),
    `seed document automation failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return notice;
}

// LLM/외부 호출 결과 토스트는 실호출 지연이 커서 호출자가 더 긴 타임아웃을 줄 수 있다.
// 기본값은 LLM 의존 단계(analyze·grade·문서분석·규격추출)에 맞춰 넉넉히 잡는다.
export async function expectToast(
  page: { getByText: (text: RegExp | string) => any },
  text: RegExp | string,
  timeout = 90_000,
) {
  await expect(page.getByText(text).first()).toBeVisible({ timeout });
}

export async function postApi(
  request: APIRequestContext,
  pathName: string,
  data: Record<string, unknown> = {},
) {
  return request.post(`${API_BASE}${pathName}`, {
    headers: apiHeaders(),
    data,
  });
}

export async function patchApi(
  request: APIRequestContext,
  pathName: string,
  data: Record<string, unknown> = {},
) {
  return request.patch(`${API_BASE}${pathName}`, {
    headers: apiHeaders(),
    data,
  });
}

export async function markRequiredChecklistReady(
  request: APIRequestContext,
  noticeNo: string,
  exceptItemIds: string[] = [],
) {
  const response = await request.get(`${API_BASE}/notices/${encodeURIComponent(noticeNo)}`, {
    headers: apiHeaders(false),
  });
  expect(
    response.ok(),
    `fetch notice failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  const notice = await response.json();
  const checklist = notice.analysis?.document_automation?.checklist || [];
  for (const item of checklist) {
    if (!item?.required || exceptItemIds.includes(item.id)) continue;
    const patch = await patchApi(
      request,
      `/notices/${encodeURIComponent(noticeNo)}/documents/checklist/${encodeURIComponent(item.id)}`,
      { status: "ready" },
    );
    expect(
      patch.ok(),
      `mark checklist ready failed: ${patch.status()} ${await patch.text()}`,
    ).toBeTruthy();
  }
}
