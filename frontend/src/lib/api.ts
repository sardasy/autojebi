/**
 * autojebi API client (M7 minimal 읽기전용).
 *
 * 모든 fetch는 cache: "no-store" — Server Component에서 매번 신선한 데이터.
 * Server Component 환경에서 NEXT_PUBLIC_API_BASE 또는 INTERNAL_API_BASE 사용.
 */

const PUBLIC_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8001";
// 컨테이너 내부에선 INTERNAL_API_BASE (예: http://api:8000)로 SSR 호출 — 옵션.
const INTERNAL_API_BASE = process.env.INTERNAL_API_BASE || PUBLIC_API_BASE;

// M9: server-side에서만 읽음 (NEXT_PUBLIC_ 안 함 — 브라우저 노출 0)
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || "";

function defaultHeaders(includeContentType = false): Record<string, string> {
  const h: Record<string, string> = {};
  if (includeContentType) h["Content-Type"] = "application/json";
  if (INTERNAL_API_KEY) h["X-API-Key"] = INTERNAL_API_KEY;
  return h;
}

export type Status =
  | "collected"
  | "analyzed"
  | "attachments_fetched"
  | "documents_analyzed"
  | "spec_extracted"
  | "hwp_composed"
  | "form_filled"
  | "notified"
  | "digest_queued"
  | "archived_low";

export type Category = "HIL" | "SW" | "IGBT" | "SCR" | "수동소자" | "ABB장비" | "혼합" | "비분류";

export interface NoticeRecord {
  notice_no: string;
  title: string | null;
  source: string | null;
  raw: Record<string, unknown> | null;
  category: string;
  fit_score: number;
  assignee: string;
  analysis: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
  // G2B 수집 컬럼 (백엔드 bid_pipeline 정규 컬럼) — raw fallback 대신 우선 사용
  bid_no: string | null;
  bid_seq: string | null;
  bid_type: string | null;
  org_code: string | null;
  org_name: string | null;
  base_price: number | null;
  open_date: string | null;
  close_date: string | null;
  collected_at: string | null;
  // M3 grading (optional)
  score_spec: number | null;
  score_qual: number | null;
  score_price: number | null;
  score_total: number | null;
  grade_reason: string | null;
  risk_note: string | null;
  top_sku: string | null;
  top_sku_name: string | null;
  sku_match_score: number | null;
  graded_at: string | null;
  unresolved_error_count?: number;
  export_count?: number;
  spec_item_count?: number;
}

export interface NoticeListResponse {
  items: NoticeRecord[];
  // 검색 확장 — 백엔드가 기본값으로 채워주므로 옵셔널이지만 항상 옴 (호환 위해 ?)
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

export interface NoticeSummary {
  active_total: number;
  closing_today: number;
  closing_7d: number;
  needs_analysis: number;
  needs_grade: number;
  ready_for_submission: number;
  blocked_documents: number;
}

export type Lifecycle = "active" | "closed" | "unknown" | "all";
export type SortField =
  | "close_date"
  | "updated_at"
  | "base_price"
  | "fit_score"
  | "score_total";
export type SortDirection = "asc" | "desc";

export interface Healthz {
  ok: boolean;
  checks: Record<string, string>;
}

export interface ListFilters {
  // 통합 키워드
  q?: string;
  // 다중 선택
  status?: string[];
  category?: string[];
  bid_type?: string[];
  source?: string[];
  // 단일 텍스트
  org_name?: string;
  assignee?: string;
  // 점수·가격 범위
  min_fit_score?: number;
  max_fit_score?: number;
  min_score_total?: number;
  max_score_total?: number;
  min_base_price?: number;
  max_base_price?: number;
  // 날짜 범위 (ISO 8601)
  open_from?: string;
  open_to?: string;
  close_from?: string;
  close_to?: string;
  // 라이프사이클
  lifecycle?: Lifecycle;
  // 존재 조건
  has_grade?: boolean;
  has_documents?: boolean;
  has_uploads?: boolean;
  ready_for_submission?: boolean;
  // 정렬·페이지네이션
  sort?: SortField;
  direction?: SortDirection;
  page?: number;
  page_size?: number;
}

type QsValue = string | number | boolean | string[] | number[] | undefined | null;

function qs(params: Record<string, QsValue>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      for (const item of v) {
        if (item === undefined || item === null || item === "") continue;
        sp.append(k, String(item));
      }
      continue;
    }
    if (typeof v === "boolean") {
      sp.set(k, v ? "true" : "false");
      continue;
    }
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// 테스트에서 qs round-trip 검증을 위해 export
export { qs };

export async function listNotices(filters: ListFilters = {}): Promise<NoticeListResponse> {
  const url = `${INTERNAL_API_BASE}/notices${qs(filters as Record<string, QsValue>)}`;
  const r = await fetch(url, { cache: "no-store", headers: defaultHeaders() });
  if (!r.ok) {
    throw new Error(`GET /notices failed: ${r.status} ${r.statusText}`);
  }
  return r.json();
}

export async function getNoticeSummary(): Promise<NoticeSummary> {
  const r = await fetch(`${INTERNAL_API_BASE}/notices/summary`, {
    cache: "no-store",
    headers: defaultHeaders(),
  });
  if (!r.ok) {
    throw new Error(`GET /notices/summary failed: ${r.status} ${r.statusText}`);
  }
  return r.json();
}

export async function getNotice(noticeNo: string): Promise<NoticeRecord> {
  const url = `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}`;
  const r = await fetch(url, { cache: "no-store", headers: defaultHeaders() });
  if (r.status === 404) {
    throw new Error("notice not found");
  }
  if (!r.ok) {
    throw new Error(`GET /notices/${noticeNo} failed: ${r.status}`);
  }
  return r.json();
}

export async function getHealth(): Promise<Healthz> {
  // healthz는 인증 불필요지만 일관성 위해 헤더 자동 부착
  const r = await fetch(`${INTERNAL_API_BASE}/healthz`, {
    cache: "no-store",
    headers: defaultHeaders(),
  });
  return r.json();
}

// ────────────────────────────────────────────────────────────
// M8: 액션 엔드포인트 (POST)
// ────────────────────────────────────────────────────────────

export interface NoticeAnalyzeResponse {
  notice_no: string;
  category: string;
  fit_score: number;
  assignee: string;
  analysis: Record<string, unknown>;
  status: string;
}

export interface NoticeGradeResponse {
  notice_no: string;
  score_spec: number;
  score_qual: number;
  score_price: number;
  score_total: number;
  top_sku: string | null;
  top_sku_name: string | null;
  grade_reason: string;
  risk_note: string | null;
  slack_delivered: boolean;
  status: string;
}

export interface NotifyResponse {
  notice_no: string;
  status: string;
  delivered: boolean;
}

export interface AutofillFormRequest {
  template_path: string;
  output_path: string;
  values: Record<string, string>;
  visible: boolean;
}

export interface AutofillFormResponse {
  notice_no: string;
  status: string;
  template_path: string;
  output_path: string;
  replaced: string[];
  missing: string[];
  remaining_placeholders: string[];
}

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

export interface HwpAgentHealthResponse {
  ok: boolean;
  base_url: string;
  detail?: string | null;
}

export type ExportKind = "excel" | "hwp" | "bid_form_hwp" | "proposal_hwp";

export interface ExportRecord {
  id?: number | null;
  kind: ExportKind;
  draft_id: string;
  output_path: string;
  mime: string;
  generated_at: string;
  notes?: string | null;
  version?: string | null;
  template_version?: string | null;
  validation_status?: "passed" | "warning" | "failed" | null;
  validation_errors?: Array<Record<string, unknown>>;
  file_size?: number | null;
  sha256?: string | null;
}

export interface ExportResponse {
  notice_no: string;
  export: ExportRecord;
}

export type SpecItemStatus = "candidate" | "reviewed" | "matched" | "gap" | "ignored";

export interface NoticeSpecItem {
  id: number;
  notice_no: string;
  item_key: string;
  label: string;
  required_value?: string | null;
  proposed_value?: string | null;
  unit?: string | null;
  category: string;
  source: string;
  confidence: number;
  evidence: Record<string, unknown>;
  status: SpecItemStatus;
  sort_order: number;
  note?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  locked_fields?: string[];
  source_text?: string | null;
  source_file_name?: string | null;
  source_page?: string | null;
  review_priority?: "normal" | "high";
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SpecItemListResponse {
  notice_no: string;
  items: NoticeSpecItem[];
}

export interface SpecItemExtractResponse extends SpecItemListResponse {
  upserted: number;
}

export interface SpecItemUpdateRequest {
  required_value?: string | null;
  proposed_value?: string | null;
  unit?: string | null;
  category?: string | null;
  source?: string | null;
  confidence?: number | null;
  evidence?: Record<string, unknown> | null;
  status?: SpecItemStatus | null;
  sort_order?: number | null;
  note?: string | null;
  reviewed_by?: string | null;
  locked_fields?: string[] | null;
  source_text?: string | null;
  source_file_name?: string | null;
  source_page?: string | null;
  review_priority?: "normal" | "high" | null;
}

export interface HwpComposeRequest {
  bid_form_template_path?: string;
  bid_form_output_path?: string | null;
  values?: Record<string, string>;
  visible?: boolean;
  include_bid_form?: boolean;
  include_technical_compliance?: boolean;
}

export interface HwpComposeBidFormResult {
  template_path: string;
  output_path: string;
  replaced: string[];
  missing: string[];
  remaining_placeholders: string[];
}

export type HwpReviewStatus = "pending" | "approved" | "rejected";

export interface HwpJobRecord {
  id: number;
  notice_no: string;
  template_id?: number | null;
  export_id?: number | null;
  status: string;
  input_values: Record<string, string>;
  replaced: string[];
  missing: string[];
  remaining_placeholders: string[];
  error_detail?: string | null;
  review_status: HwpReviewStatus;
  review_note?: string | null;
  reviewed_by?: string | null;
}

export interface HwpContextRequest {
  template_key?: string;
  values_override?: Record<string, string>;
}

export interface HwpContextResponse {
  notice_no: string;
  template: HwpTemplateRecord;
  context: Record<string, unknown>;
  input_values: Record<string, string>;
  required_missing: string[];
}

export interface HwpPutFieldsRequest {
  template_key?: string;
  output_path?: string | null;
  values_override?: Record<string, string>;
  visible?: boolean;
}

export interface HwpPutFieldsResponse {
  notice_no: string;
  status: string;
  export?: ExportRecord | null;
  job: HwpJobRecord;
  required_missing: string[];
  remaining_placeholders: string[];
  errors: { stage?: string; detail?: string }[];
}

export interface HwpJobReviewRequest {
  review_status: HwpReviewStatus;
  review_note?: string | null;
  reviewed_by?: string | null;
}

export interface HwpTemplateFieldMapping {
  id?: number | null;
  hwp_field_name: string;
  context_path: string;
  value_type: string;
  required: boolean;
  default_value?: string | null;
  transform: string;
  sort_order: number;
  active: boolean;
}

export interface HwpTemplateRecord {
  id: number;
  template_key: string;
  kind: "bid_form" | "proposal";
  name: string;
  template_path: string;
  template_version?: string | null;
  active: boolean;
  mappings: HwpTemplateFieldMapping[];
}

export interface HwpTemplateListResponse {
  items: HwpTemplateRecord[];
}

export interface HwpComposeResponse {
  notice_no: string;
  status: string;
  bid_form?: HwpComposeBidFormResult | null;
  technical_compliance?: ExportRecord | null;
  job?: HwpJobRecord | null;
  required_missing: string[];
  remaining_placeholders: string[];
  errors: { stage?: string; detail?: string }[];
}

export interface ProposalComposeRequest {
  template_path?: string;
  output_path?: string | null;
  values_override?: Record<string, string>;
  visible?: boolean;
}

export interface ProposalComposeResponse {
  notice_no: string;
  export?: ExportRecord | null;
  proposal: Record<string, unknown>;
  job?: HwpJobRecord | null;
  required_missing: string[];
  remaining_placeholders: string[];
  errors: { stage?: string; detail?: string }[];
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

export interface NoticeUpsertRequest {
  notice_no: string;
  title?: string;
  source?: string;
  raw?: Record<string, unknown>;
}

export interface IngestRequest {
  source?: string;
  skus?: unknown[];
}

export interface IngestResult {
  ingested: number;
  collection: string;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${INTERNAL_API_BASE}${path}`, {
    method: "POST",
    headers: defaultHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    let detail: string;
    try {
      const j = await r.json();
      detail = j?.detail ? JSON.stringify(j.detail) : r.statusText;
    } catch {
      detail = r.statusText;
    }
    throw new Error(`POST ${path} failed: ${r.status} ${detail}`);
  }
  return r.json();
}

export async function upsertNotice(payload: NoticeUpsertRequest): Promise<NoticeRecord> {
  return postJson<NoticeRecord>("/notices/upsert", payload);
}

export async function analyzeNotice(noticeNo: string): Promise<NoticeAnalyzeResponse> {
  return postJson<NoticeAnalyzeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/analyze`,
    {},
  );
}

export async function gradeNotice(
  noticeNo: string,
  alert: boolean,
): Promise<NoticeGradeResponse> {
  return postJson<NoticeGradeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/grade`,
    { alert },
  );
}

export async function notifyNotice(
  noticeNo: string,
  dryRun: boolean,
): Promise<NotifyResponse> {
  return postJson<NotifyResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/notify`,
    { dry_run: dryRun },
  );
}

export async function autofillForm(
  noticeNo: string,
  payload: AutofillFormRequest,
): Promise<AutofillFormResponse> {
  return postJson<AutofillFormResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/autofill-form`,
    payload,
  );
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

export async function extractSpecItems(noticeNo: string): Promise<SpecItemExtractResponse> {
  return postJson<SpecItemExtractResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/spec-items/extract`,
    {},
  );
}

export async function listSpecItems(noticeNo: string): Promise<SpecItemListResponse> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/spec-items`,
    { headers: defaultHeaders(), cache: "no-store" },
  );
  if (!r.ok) throw new Error(`GET spec items failed: ${r.status}`);
  return r.json();
}

export async function updateSpecItem(
  noticeNo: string,
  itemId: number,
  payload: SpecItemUpdateRequest,
): Promise<NoticeSpecItem> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/spec-items/${itemId}`,
    {
      method: "PATCH",
      headers: defaultHeaders(true),
      body: JSON.stringify(payload),
      cache: "no-store",
    },
  );
  if (!r.ok) throw new Error(`PATCH spec item failed: ${r.status}`);
  return r.json();
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

export async function ingestSkus(payload: IngestRequest = {}): Promise<IngestResult> {
  return postJson<IngestResult>("/skus/ingest", payload);
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

export async function getHwpAgentHealth(): Promise<HwpAgentHealthResponse> {
  const r = await fetch(`${INTERNAL_API_BASE}/documents/hwp-agent/health`, {
    headers: defaultHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`GET hwp agent health failed: ${r.status}`);
  return r.json();
}

export async function listHwpTemplates(): Promise<HwpTemplateListResponse> {
  const r = await fetch(`${INTERNAL_API_BASE}/documents/hwp-templates`, {
    headers: defaultHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`GET hwp templates failed: ${r.status}`);
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

export async function composeHwpDocuments(
  noticeNo: string,
  payload: HwpComposeRequest,
): Promise<HwpComposeResponse> {
  return postJson<HwpComposeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-compose`,
    payload,
  );
}

export async function previewHwpContext(
  noticeNo: string,
  payload: HwpContextRequest,
): Promise<HwpContextResponse> {
  return postJson<HwpContextResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-context`,
    payload,
  );
}

export async function putHwpFields(
  noticeNo: string,
  payload: HwpPutFieldsRequest,
): Promise<HwpPutFieldsResponse> {
  return postJson<HwpPutFieldsResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-put-fields`,
    payload,
  );
}

export async function reviewHwpJob(
  noticeNo: string,
  jobId: number,
  payload: HwpJobReviewRequest,
): Promise<{ notice_no: string; job: HwpJobRecord }> {
  return postJson<{ notice_no: string; job: HwpJobRecord }>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-jobs/${jobId}/review`,
    payload,
  );
}

export async function composeProposalDocument(
  noticeNo: string,
  payload: ProposalComposeRequest,
): Promise<ProposalComposeResponse> {
  return postJson<ProposalComposeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/proposal-compose`,
    payload,
  );
}

// M12 — KJEBI 메일 paste-UI 추출

export interface KjebiMailExtraction {
  notice_no?: string | null;
  title?: string | null;
  org_name?: string | null;
  close_date?: string | null;
  base_price?: number | null;
  bid_url?: string | null;
  summary?: string | null;
}

export interface MailExtractRequest {
  raw_text: string;
  source?: string;
}

export interface MailExtractResponse {
  extracted: KjebiMailExtraction;
  upserted: NoticeRecord | null;
  confidence: number;
  errors: string[];
}

export async function extractFromMail(
  payload: MailExtractRequest,
): Promise<MailExtractResponse> {
  return postJson<MailExtractResponse>("/notices/extract-from-mail", payload);
}

// M13 — G2B 라이브 검색 (등록 전 공고 확인)

export interface NoticeSearchRequest {
  keyword: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
}

export interface NoticeSearchItem {
  notice_no: string;
  title: string;
  source: string;
  org_name: string | null;
  base_price: number | null;
  open_date: string | null;
  close_date: string | null;
  raw: Record<string, unknown>;
  already_exists: boolean;
}

export interface NoticeSearchResponse {
  items: NoticeSearchItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function searchG2BNotices(
  payload: NoticeSearchRequest,
): Promise<NoticeSearchResponse> {
  return postJson<NoticeSearchResponse>("/notices/search", payload);
}

/**
 * 백엔드 다운로드 URL을 그대로 호출해 blob을 받는 서버사이드 헬퍼.
 * X-API-Key 헤더 자동 첨부. Next.js API route (route.ts)에서 사용.
 */
export async function fetchDownloadBlob(path: string): Promise<Response> {
  return fetch(`${INTERNAL_API_BASE}${path}`, {
    headers: defaultHeaders(),
    cache: "no-store",
  });
}
