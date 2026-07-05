// ────────────────────────────────────────────────────────────
// M8: 액션 엔드포인트 (POST)
// ────────────────────────────────────────────────────────────

import { postJson } from "./client";

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
