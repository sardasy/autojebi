/** Additive /v2 readiness contract. Predicates and Korean messages live on the server. */
export type ReadinessCode =
  | "source_changed"
  | "deadline_unknown"
  | "deadline_timezone_unknown"
  | "deadline_passed"
  | "attachment_missing"
  | "attachment_unread"
  | "source_need_unresolved"
  | "form_review_required"
  | "form_layout_stale"
  | "form_reference_stale"
  | "writing_output_missing"
  | "spec_review_required"
  | "writing_plan_stale"
  | "writing_target_empty"
  | "source_review_required"
  | "asset_stale"
  | "asset_disabled"
  | "asset_expired"
  | "asset_not_yet_valid"
  | "asset_validity_unknown"
  | "asset_subject_mismatch"
  | "source_extraction_required"
  | "evidence_unconfirmed"
  | "requirements_missing"
  | "requirement_review_required"
  | "requirement_compliance_required"
  | "commercial_review_required"
  | "proposal_review_required"
  | "proposal_coverage_missing"
  | "source_checksum_missing"
  | "source_file_invalid"
  | "hwp_output_missing"
  | "excel_output_missing"
  | "artifact_review_required"
  | "artifact_warning"
  | "form_retired";
export interface ReadinessIssue {
  code: ReadinessCode;
  scope: "workspace" | "notice" | "attachment" | "source_need" | "document" | "form"
    | "writing_target" | "requirement" | "checklist" | "commercial" | "proposal" | "artifact";
  entity_id: string | null;
  blocking: boolean;
  message_params: Record<string, string>;
  message: string;
  next_action: string;
}
