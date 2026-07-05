// ── 필요서류 자동확인 (notice_required_documents) ──────────────────────────

import { defaultHeaders, INTERNAL_API_BASE, postJson } from "./client";

export type RequirementType =
  | "required"
  | "conditional"
  | "winner_only"
  | "contract_stage"
  | "reference";
export type SubmitStage =
  | "bid"
  | "proposal"
  | "price"
  | "post_award"
  | "contract"
  | "delivery"
  | "conditional";

export interface NoticeRequiredDocument {
  id: number;
  notice_no: string;
  doc_name: string;
  requirement_type: RequirementType;
  submit_stage: SubmitStage;
  source_file?: string | null;
  evidence_text?: string | null;
  page_no?: number | null;
  deadline?: string | null;
  condition?: string | null;
  confidence: number;
  checked: boolean;
  owner?: string | null;
  note?: string | null;
}

export type RequiredDocsStopPoint =
  | "no_uploads"
  | "no_text"
  | "no_candidates"
  | "no_classification"
  | "ok";

export interface RequiredDocumentDiagnostics {
  uploads: number;
  files_extracted: number;
  total_chars: number;
  candidates: number;
  classified: number;
  stopped_at: RequiredDocsStopPoint;
}

export interface RequiredDocumentListResponse {
  notice_no: string;
  items: NoticeRequiredDocument[];
  diagnostics?: RequiredDocumentDiagnostics | null;
}

export interface RequiredDocumentAnalyzeResponse {
  notice_no: string;
  items: NoticeRequiredDocument[];
  upserted: number;
  diagnostics?: RequiredDocumentDiagnostics | null;
  errors: { stage?: string; detail?: string }[];
}

export interface RequiredDocumentUpdateRequest {
  checked?: boolean;
  owner?: string | null;
  note?: string | null;
}

export async function analyzeRequiredDocuments(
  noticeNo: string,
): Promise<RequiredDocumentAnalyzeResponse> {
  return postJson<RequiredDocumentAnalyzeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/required-documents/analyze`,
    {},
  );
}

export async function listRequiredDocuments(
  noticeNo: string,
): Promise<RequiredDocumentListResponse> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/required-documents`,
    { headers: defaultHeaders(), cache: "no-store" },
  );
  if (!r.ok) throw new Error(`GET required documents failed: ${r.status}`);
  return r.json();
}

export async function checkRequiredDocument(
  noticeNo: string,
  docId: number,
  payload: RequiredDocumentUpdateRequest,
): Promise<NoticeRequiredDocument> {
  const r = await fetch(
    `${INTERNAL_API_BASE}/notices/${encodeURIComponent(noticeNo)}/required-documents/${docId}`,
    {
      method: "PATCH",
      headers: defaultHeaders(true),
      body: JSON.stringify(payload),
      cache: "no-store",
    },
  );
  if (!r.ok) throw new Error(`PATCH required document failed: ${r.status}`);
  return r.json();
}
