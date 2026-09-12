export interface SourceDocument {
  id: string; name: string; role: "notice_source" | "company_evidence" | "product_evidence" | "company_reference";
  confirmed: boolean; text: string; text_origin: string; item_id?: string | null;
  attachment_index?: number; attachment_url?: string;
  company_asset?: {id:string; version:number; expires_on:string|null; no_expiry:boolean; stale:boolean};
  asset_issue?: string;
  extraction?: {version?: number; complete: boolean;
    pages?: {page_no: number; method: string; status: string; review_required: boolean; code?: string; confidence?: number | null}[];
    cells?: {sheet: string; cell: string; value: string | number | boolean | null; formula: string | null}[];
    items?: {sheet: string; row: string; review_status: string}[];
    issues?: {code: string; sheet: string; cell: string}[];
    members?: {name: string; sha256: string; size: number; status: string; complete: boolean}[]};
}
export interface SourceAttachment {
  index: number; name: string; url: string; document_ids: string[];
  state: "missing" | "unread" | "ready";
}
export interface Requirement {
  id: string; text: string; document_id: string; quote: string; locator: string;
  category: "technical" | "qualification" | "document" | "schedule"; mandatory: boolean;
  proposed_value: string; evidence_id: string | null; evidence_quote: string; evidence_locator: string;
  review_status: "pending" | "accepted" | "rejected";
  compliance?: "meets" | "does_not_meet" | "unassessed";
  proposal_disposition?: "include" | "evidence_only"; proposal_note?: string;
}
export interface WorkspaceJob {
  execution_lane?: "local" | "external";
  id: string; kind: string; input_version: number; status: string; quality: string | null;
  result: { artifact?: string; warnings?: string[]; sections?: { text: string }[]; required_missing?: string[];
    quote_diagnostics?: QuoteDiagnostic[];
    pages?: {number: number; width: number; height: number; sha256: string}[];
    documents?: {id: string; role?: SourceDocument["role"]; text?: string; format?: string; attachment_index?: number | null}[];
    inspection_passed?: boolean; fields?: string[]; unmapped?: string[];
    missing?: string[]; remaining_placeholders?: string[]; verified?: boolean;
    axes?: Record<string, {score: number | null; state: string; reason: string}>;
    score_total?: number | null; technical_coverage?: number | null;
    candidates?: {sku: {sku_id: string; name?: string; brand?: string}; similarity: number; review_status: string}[];
    qualification_references?: {reason: string; references: {licenses: string[]; regions: string[]; permitted_industries: string[]} | null};
  } | null;
  error: { code: string; message: string; next_action: string; operation?: {operation_id?: string; failure_stage?: string; stage?: string} } | null;
  created_at: string; finished_at: string | null;
  parameters?: {template_key?: string; recovery_of?: string};
}
export interface WritingReference {document_id: string; name?: string; quote: string; input_version?: number}
export interface WebWritingReference {title: string; url: string; quote: string; verified?: boolean}
export interface FormFilling {
  document_id: string; name?: string; source_sha256: string; input_version: number;
  review_status: string;
  fields: {field_id: string; value: string;
    reference?: {document_id: string; quote: string};
    web_reference?: {title: string; url: string; quote: string}}[];
}
export type DocumentKind = "qualitative_proposal" | "bid_document" | "other_document";
export interface WritingPlanItem {id:string; title:string; document_kind:DocumentKind; action:"write"|"attach"|"electronic"; document_id:string; quote:string}
export interface Workspace {
  spec_compliance?: "충족" | "불충족" | "미확인" | "일부미확인";
  unresolved_spec_count?: number;
  spec_source_complete?: boolean;
  writing_plan_current?: boolean;
  notice_no: string; version: number; decision: string; ready: boolean; source_changed: boolean;
  source_attachments?: SourceAttachment[];
  source_needs?: SourceNeed[];
  inputs: { notice: { title: string | null; org_name: string | null; close_date: string | null; base_price: number | null };
    documents: SourceDocument[]; requirements: Requirement[]; checklist: {id: string; name: string}[];
    writing_plan?: {items:WritingPlanItem[]; reviewed_at:string; reviewed_version:number};
    form_fillings?: FormFilling[];
    source_reviewed: boolean; legacy_warning: boolean; company: Record<string, unknown>;
    commercial?: {offer_price: number; quantity: number; document_id: string; quote: string; locator: string; note: string};
    proposal_sections?: {id: string; text: string; review_status: string; evidence_ids: string[]; requirement_ids?: string[]; reference?: {document_id: string; name?: string; quote: string; input_version: number}; document_kind?: DocumentKind; title?: string; references?: WritingReference[]; web_references?: WebWritingReference[]}[] };
  proposal_coverage?: {mandatory_count: number; covered_count: number; evidence_only_count: number; missing_ids: string[]};
  blockers: string[]; next_action: string; jobs: WorkspaceJob[];
  reviews: {id: string; job_id: string | null; action: string; note: string; input_version: number; created_at: string}[];
}
export const decisions: Record<string, string> = {pending: "미결정", participate: "참가", hold: "보류", decline: "불참"};
export const jobNames: Record<string, string> = {spec_index: "사양 검색 색인", fetch: "첨부 가져오기", extract: "본문 추출", analyze: "요구사항 분석", grade: "규격·자격·가격 검토", proposal: "검토 초안", verify: "누락 검사", excel: "Excel 생성", hwp: "HWP 생성", hwp_inspect: "템플릿 필드 검사", package: "검토 패키지", notify: "알림 미리보기"};
export const jobStates: Record<string, string> = {queued: "대기", running: "처리 중", succeeded: "완료", failed: "실패", blocked: "차단"};
export interface QuoteDiagnostic {
  candidate_id: string; status: "exact" | "whitespace" | "ambiguous" | "mismatch" | "invalid_structure";
  requirement?: Pick<Requirement, "text" | "quote" | "document_id" | "locator" | "category" | "mandatory">;
  matches: {start: number; end: number; quote: string}[];
}
export interface SourceNeed {
  id: string; name: string; state: "missing" | "linked" | "not_applicable";
  linked_document_id: string; note: string; resolution_quote: string;
  mentions: {document_id: string; quote: string; start: number}[];
}
export async function workspaceApi<T>(path: string, body?: unknown, method?: "POST" | "PUT"): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api/v2${path}`, {method: body === undefined ? "GET" : method || "POST",
    headers: body === undefined || form ? undefined : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : form ? body : JSON.stringify(body), cache: "no-store"});
  if (!response.ok) {
    const json = await response.json().catch(() => ({}));
    const detail = json.detail;
    throw new Error(typeof detail === "object" && !Array.isArray(detail) ? `${detail.message || "요청 실패"} ${detail.next_action || ""}` : typeof detail === "string" ? detail : "입력값을 확인하세요.");
  }
  return response.json() as Promise<T>;
}
