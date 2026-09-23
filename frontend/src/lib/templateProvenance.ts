export interface TemplateProvenance {
  state: "validation_only" | "reviewed_source" | "unclassified" | "untracked" | "invalid" | "unavailable";
  template_key: string | null; template_path: string | null; template_sha256: string | null;
  metadata_sha256: string | null; generation_allowed: boolean; approval_allowed: boolean;
  content_record_sha256: string | null; warning: string | null;
}

export interface WorkspaceTemplate {
  template_key: string; name: string; provenance?: TemplateProvenance;
}

export function templateProvenanceWarning(value?: TemplateProvenance, key?: string): string | null {
  if (value && !value.approval_allowed) return value.warning || "템플릿 출처 확인 전에는 제출용 파일을 승인할 수 없습니다.";
  if (!value && (key === "bid_form" || key === "proposal")) return "기본 템플릿의 출처 기록이 없어 제출용 파일 승인을 차단합니다. 원본과 생성 기록을 확인하세요.";
  return null;
}

export function templateLabel(template: WorkspaceTemplate): string {
  const state = template.provenance?.state;
  return template.name + (state === "validation_only" ? " · 검증 전용 골격" :
    state === "reviewed_source" ? " · 원본 출처 확인됨" : state && state !== "untracked" ? " · 출처 확인 필요" : "");
}
