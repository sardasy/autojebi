import { defaultHeaders, INTERNAL_API_BASE, postJson } from "./client";
import type { HwpJobRecord } from "./hwp";
import type { ExportKind, ExportRecord } from "./types";

export type DocumentItemType =
  | "company_common"
  | "bid_form"
  | "technical"
  | "qualification"
  | "price"
  | "contract"
  | "other";

export type DocumentItemStatus =
  | "needed"
  | "ready"
  | "generated"
  | "blocked"
  | "not_applicable";

export type DocumentRole =
  | "submit_required"
  | "reference_only"
  | "qualification_evidence"
  | "price_document"
  | "internal_prep";

export interface DocumentChecklistItem {
  id: string;
  name: string;
  type: DocumentItemType;
  required: boolean;
  status: DocumentItemStatus;
  owner: string | null;
  reason: string | null;
  source: string;
  due_hint: string | null;
  note?: string | null;
  document_role?: DocumentRole | null;
}

export interface DocumentAutomationResult {
  checklist: DocumentChecklistItem[];
  drafts: Record<string, unknown>;
  risks: string[];
  generated_at: string;
  source: string;
  ready_for_submission: boolean;
  missing_required: DocumentChecklistItem[];
  errors: Array<Record<string, unknown>>;
  // M11 v2 — 사용자 업로드/내보내기 메타데이터
  uploads?: UploadedDocument[];
  exports?: ExportRecord[];
  hwp_jobs?: HwpJobRecord[];
}

export interface UploadedDocument {
  id: string;
  name: string;
  size: number;
  mime: string;
  item_id?: string | null;
  storage_path: string;
  uploaded_at: string;
  sha256?: string | null;
  detected_item_id?: string | null;
  detect_confidence?: number | null;
  analysis_summary?: string | null;
  text_extract_error?: string | null;
  source_ref?: "uploaded" | "common_library" | "g2b_attachment" | null;
}

export interface UploadResponse {
  notice_no: string;
  uploaded: UploadedDocument;
}

export interface UploadListResponse {
  notice_no: string;
  items: UploadedDocument[];
}

export type AttachmentFetchJobStatus = "completed" | "completed_with_errors";
export type AttachmentFetchFileStatus = "pending" | "success" | "failed" | "skipped";

export interface AttachmentFetchFileResult {
  id: number;
  filename: string;
  url: string;
  status: AttachmentFetchFileStatus;
  upload_id?: string | null;
  error?: string | null;
  source_ref: "g2b_attachment";
}

export interface AttachmentFetchResponse {
  notice_no: string;
  job_id?: number | null;
  status: AttachmentFetchJobStatus;
  files: AttachmentFetchFileResult[];
  fetched: UploadedDocument[];
  errors: Array<Record<string, unknown>>;
}

export interface CommonUploadResponse {
  uploaded: UploadedDocument;
}

export interface CommonUploadListResponse {
  items: UploadedDocument[];
}

export interface ExportResponse {
  notice_no: string;
  export: ExportRecord;
}

export interface DocumentAutomationResponse {
  notice_no: string;
  document_automation: DocumentAutomationResult;
}

export interface ChecklistUpdateRequest {
  status?: DocumentItemStatus;
  owner?: string;
  note?: string;
}

export interface DocumentValidationResponse {
  notice_no: string;
  ready_for_submission: boolean;
  missing_required: DocumentChecklistItem[];
  checklist: DocumentChecklistItem[];
}

export async function analyzeDocuments(
  noticeNo: string,
): Promise<DocumentAutomationResponse> {
  return postJson<DocumentAutomationResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/analyze`,
    {},
  );
}

export async function fetchG2BAttachments(
  noticeNo: string,
): Promise<AttachmentFetchResponse> {
  return postJson<AttachmentFetchResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/attachments/fetch`,
    {},
  );
}

export async function updateDocumentChecklistItem(
  noticeNo: string,
  itemId: string,
  payload: ChecklistUpdateRequest,
): Promise<DocumentAutomationResponse> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(
      noticeNo,
    )}/documents/checklist/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      headers: defaultHeaders(true),
      body: JSON.stringify(payload),
      cache: "no-store",
    },
  );
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j?.detail ? JSON.stringify(j.detail) : detail;
    } catch {
      // keep status text
    }
    throw new Error(`PATCH checklist failed: ${r.status} ${detail}`);
  }
  return r.json();
}

export async function validateDocuments(
  noticeNo: string,
): Promise<DocumentValidationResponse> {
  return postJson<DocumentValidationResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/validate`,
    {},
  );
}

// M11 v2 — 파일 업로드/다운로드/내보내기

export async function uploadDocument(
  noticeNo: string,
  file: File,
  itemId?: string,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (itemId) form.append("item_id", itemId);
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/documents/uploads`,
    {
      method: "POST",
      headers: defaultHeaders(false), // Content-Type은 FormData가 자동 설정
      body: form,
      cache: "no-store",
    },
  );
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j?.detail ? JSON.stringify(j.detail) : detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(`POST upload failed: ${r.status} ${detail}`);
  }
  return r.json();
}

export async function listDocumentUploads(noticeNo: string): Promise<UploadListResponse> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/documents/uploads`,
    { headers: defaultHeaders(), cache: "no-store" },
  );
  if (!r.ok) throw new Error(`GET uploads failed: ${r.status}`);
  return r.json();
}

export async function uploadCommonDocument(
  file: File,
  itemId?: string,
): Promise<CommonUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (itemId) form.append("item_id", itemId);
  const r = await fetch(`${INTERNAL_API_BASE}/documents/common/uploads`, {
    method: "POST",
    headers: defaultHeaders(false),
    body: form,
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`POST common upload failed: ${r.status}`);
  return r.json();
}

export async function listCommonUploads(): Promise<CommonUploadListResponse> {
  const r = await fetch(`${INTERNAL_API_BASE}/documents/common/uploads`, {
    headers: defaultHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`GET common uploads failed: ${r.status}`);
  return r.json();
}

export async function importCommonUpload(
  noticeNo: string,
  uploadId: string,
): Promise<UploadResponse> {
  return postJson<UploadResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/import-common/${encodeURIComponent(uploadId)}`,
    {},
  );
}

export async function deleteDocumentUpload(
  noticeNo: string,
  uploadId: string,
): Promise<{ notice_no: string; deleted: string }> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/documents/uploads/${encodeURIComponent(uploadId)}`,
    { method: "DELETE", headers: defaultHeaders(), cache: "no-store" },
  );
  if (!r.ok) throw new Error(`DELETE upload failed: ${r.status}`);
  return r.json();
}

export async function exportDocument(
  noticeNo: string,
  kind: ExportKind,
): Promise<ExportResponse> {
  return postJson<ExportResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/exports/${kind}`,
    {},
  );
}
