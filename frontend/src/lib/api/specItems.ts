import { defaultHeaders, INTERNAL_API_BASE, postJson } from "./client";

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
