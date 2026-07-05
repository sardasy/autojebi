import { defaultHeaders, INTERNAL_API_BASE, postJson, qs, type QsValue } from "./client";

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

export interface NoticeUpsertRequest {
  notice_no: string;
  title?: string;
  source?: string;
  raw?: Record<string, unknown>;
}

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

export async function upsertNotice(payload: NoticeUpsertRequest): Promise<NoticeRecord> {
  return postJson<NoticeRecord>("/notices/upsert", payload);
}
