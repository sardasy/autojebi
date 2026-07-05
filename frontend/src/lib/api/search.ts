import { postJson } from "./client";
import type { NoticeRecord } from "./notices";

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
