// documents ↔ hwp 양쪽에서 참조되는 공유 타입 (순환 import 방지 위해 승격)

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
