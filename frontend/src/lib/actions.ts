"use server";

/**
 * Next 15 App Router Server Actions (M8).
 *
 * 모든 함수는 서버사이드에서 실행되어 NEXT_PUBLIC_API_KEY 같은 anti-pattern 회피.
 * 성공 시 revalidatePath로 ISR 캐시 무효화 — 페이지가 자동으로 최신 데이터 반영.
 */

import { revalidatePath } from "next/cache";

import * as api from "./api";
import type {
  AutofillFormRequest,
  ChecklistUpdateRequest,
  ExportKind,
  HwpComposeRequest,
  ProposalComposeRequest,
  IngestRequest,
  MailExtractRequest,
  NoticeSearchItem,
  NoticeSearchRequest,
  SpecItemUpdateRequest,
  NoticeUpsertRequest,
} from "./api";

export async function actionUpsert(payload: NoticeUpsertRequest) {
  const result = await api.upsertNotice(payload);
  revalidatePath("/notices");
  return result;
}

export async function actionAnalyze(noticeNo: string) {
  const result = await api.analyzeNotice(noticeNo);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionGrade(noticeNo: string, alert: boolean) {
  const result = await api.gradeNotice(noticeNo, alert);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionNotify(noticeNo: string, dryRun: boolean) {
  const result = await api.notifyNotice(noticeNo, dryRun);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionAutofill(
  noticeNo: string,
  payload: AutofillFormRequest,
) {
  const result = await api.autofillForm(noticeNo, payload);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  return result;
}

export async function actionAnalyzeDocuments(noticeNo: string) {
  const result = await api.analyzeDocuments(noticeNo);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionFetchG2BAttachments(noticeNo: string) {
  const result = await api.fetchG2BAttachments(noticeNo);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionUpdateDocumentChecklistItem(
  noticeNo: string,
  itemId: string,
  payload: ChecklistUpdateRequest,
) {
  const result = await api.updateDocumentChecklistItem(noticeNo, itemId, payload);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionValidateDocuments(noticeNo: string) {
  const result = await api.validateDocuments(noticeNo);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionExtractSpecItems(noticeNo: string) {
  const result = await api.extractSpecItems(noticeNo);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionListSpecItems(noticeNo: string) {
  return api.listSpecItems(noticeNo);
}

export async function actionUpdateSpecItem(
  noticeNo: string,
  itemId: number,
  payload: SpecItemUpdateRequest,
) {
  const result = await api.updateSpecItem(noticeNo, itemId, payload);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  return result;
}

export async function actionIngestSkus(payload: IngestRequest = {}) {
  return api.ingestSkus(payload);
}

// M11 v2 — 파일 업로드/내보내기 Server Actions

export async function actionUploadDocument(
  noticeNo: string,
  file: File,
  itemId?: string,
) {
  const result = await api.uploadDocument(noticeNo, file, itemId);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionListDocumentUploads(noticeNo: string) {
  return api.listDocumentUploads(noticeNo);
}

export async function actionUploadCommonDocument(file: File, itemId?: string) {
  return api.uploadCommonDocument(file, itemId);
}

export async function actionListCommonUploads() {
  return api.listCommonUploads();
}

export async function actionGetHwpAgentHealth() {
  return api.getHwpAgentHealth();
}

export async function actionImportCommonUpload(noticeNo: string, uploadId: string) {
  const result = await api.importCommonUpload(noticeNo, uploadId);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionDeleteDocumentUpload(noticeNo: string, uploadId: string) {
  const result = await api.deleteDocumentUpload(noticeNo, uploadId);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionExportDocument(noticeNo: string, kind: ExportKind) {
  const result = await api.exportDocument(noticeNo, kind);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  return result;
}

export async function actionComposeHwpDocuments(
  noticeNo: string,
  payload: HwpComposeRequest,
) {
  const result = await api.composeHwpDocuments(noticeNo, payload);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

export async function actionComposeProposalDocument(
  noticeNo: string,
  payload: ProposalComposeRequest,
) {
  const result = await api.composeProposalDocument(noticeNo, payload);
  revalidatePath(`/notices/${encodeURIComponent(noticeNo)}`);
  revalidatePath("/notices");
  return result;
}

// M12 — KJEBI 메일 paste 추출 + 자동 upsert
export async function actionExtractMail(payload: MailExtractRequest) {
  const result = await api.extractFromMail(payload);
  if (result.upserted) {
    revalidatePath("/notices");
  }
  return result;
}

// M13 — G2B 라이브 검색 + 검색 결과 그대로 upsert
//
// Result 패턴: throw 대신 객체 반환 — Next.js production이 Server Action throw를
// "digest property is included on this error" 로 마스킹하기 때문. 백엔드의 정확한
// 422/502 메시지가 그대로 토스트에 노출되도록 한다.

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

export async function actionSearchG2B(
  payload: NoticeSearchRequest,
): Promise<ActionResult<Awaited<ReturnType<typeof api.searchG2BNotices>>>> {
  try {
    return { ok: true, data: await api.searchG2BNotices(payload) };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}

export async function actionUpsertFromSearchResult(
  item: NoticeSearchItem,
): Promise<ActionResult<Awaited<ReturnType<typeof api.upsertNotice>>>> {
  try {
    const result = await api.upsertNotice({
      notice_no: item.notice_no,
      title: item.title,
      source: item.source,
      raw: item.raw,
    });
    revalidatePath("/notices");
    return { ok: true, data: result };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}
