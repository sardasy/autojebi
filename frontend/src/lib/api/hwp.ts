import {
  defaultHeaders,
  INTERNAL_API_BASE,
  postComposeAllowingValidation,
  postJson,
} from "./client";
import type { ExportRecord } from "./types";

export interface HwpAgentHealthResponse {
  ok: boolean;
  base_url: string;
  detail?: string | null;
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

export async function composeHwpDocuments(
  noticeNo: string,
  payload: HwpComposeRequest,
): Promise<HwpComposeResponse> {
  return postComposeAllowingValidation<HwpComposeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/hwp-compose`,
    payload,
    (errors) => ({
      notice_no: noticeNo,
      status: "precompose_failed",
      bid_form: null,
      technical_compliance: null,
      job: null,
      required_missing: [],
      remaining_placeholders: [],
      errors,
    }),
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
  return postComposeAllowingValidation<ProposalComposeResponse>(
    `/notices/${encodeURIComponent(noticeNo)}/documents/proposal-compose`,
    payload,
    (errors) => ({
      notice_no: noticeNo,
      export: null,
      proposal: {},
      job: null,
      required_missing: [],
      remaining_placeholders: [],
      errors,
    }),
  );
}
