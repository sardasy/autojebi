export interface DocumentComparison {
  document_id: string; name: string; input_version: number;
  status: "compared" | "failed" | "skipped"; error_code?: string;
  source_sha256?: string; baseline_text?: string;
  comparison_v2?: ComparisonV2;
  reference?: {text: string; page_mode: string; warnings: string[];
    tables: {reference_table_id: string | null; locator: string; rows: number; cols: number;
      cells: {row: number; col: number; text: string}[]}[]};
  comparison?: {state: "no_baseline" | "same_tokens" | "different";
    missing_token_count: number; added_token_count: number;
    missing_examples: string[]; added_examples: string[]};
  candidate?: {text: string; page_mode: "layout" | "section" | "unknown"; warnings: string[];
    tables: {locator: string; rows: number; cols: number}[];
    fragments: {locator: string; kind: "paragraph" | "table_cell"; text: string;
      page?: number | null; row?: number | null; col?: number | null;
      row_span?: number | null; col_span?: number | null}[]};
}

export interface TextChange {
  kind: "content" | "whitespace" | "unclassified";
  before_start: number; before_end: number; after_start: number; after_end: number;
  before: string; after: string; before_context: string; after_context: string;
}
export interface TextDifference {
  before_text: string; after_text: string; changes: TextChange[];
  completion: "complete" | "truncated";
}
export interface ComparisonV2 extends TextDifference {
  comparison_version: 2; offset_unit: "unicode_codepoint"; offset_basis: "comparison_text";
  basis: string; has_baseline: boolean; truncation_reason?: string;
  summary: {content: number; whitespace: number; unclassified: number; control_groups: number;
    changed_cells: number; unmatched_tables: number; structure_changes: number; cells_not_compared: boolean};
  controls: {locator: string; text: string; start: number; end: number}[];
  tables: {reference_table_id: string | null; locator: string; parent_cell?: string | null;
    status: "matched" | "unmatched" | "structure_changed";
    cells: (TextDifference & {row: number; col: number})[]; row_diff?: TextDifference}[];
}

export function comparisonTitle(value: ComparisonV2): string {
  const s = value.summary;
  if (!value.has_baseline) return "기존 본문 없음 · 원문 대조 필요";
  const title = s.content ? `본문 변경 ${s.content}구간`
    : value.completion !== "complete" ? "본문 변경 미발견 · 전체 비교 미완료"
    : s.unclassified ? `분류 미확인 ${s.unclassified}건` : "본문 내용 차이 없음";
  return [title, s.changed_cells ? `표 ${s.changed_cells}셀 변경` : "",
    s.structure_changes ? `표 ${s.structure_changes}개 구조 변경` : "",
    s.unmatched_tables ? `표 ${s.unmatched_tables}개 구조 대응 확인 필요` : "",
    s.cells_not_compared ? "표 셀 미비교" : ""].filter(Boolean).join(" · ");
}
