import type {Requirement} from "./workspace";

export type RequirementIdentity = Pick<Requirement, "document_id" | "quote" | "text">;

/** Mirrors api/workspace/quote_recovery.py `is_duplicate_requirement`: same source document and same quote or text. */
export const isDuplicateRequirement = (existing: RequirementIdentity[], item: Partial<RequirementIdentity>) =>
  existing.some(r => r.document_id === item.document_id && (r.quote === item.quote || r.text === item.text));

/** Status text for 결과 반영 on an analysis job, naming the results the server skips as duplicates. */
export function applyResultMessage(existing: RequirementIdentity[], results: RequirementIdentity[] = []): string {
  const kept = [...existing];
  let skipped = 0;
  for (const item of results) {
    if (isDuplicateRequirement(kept, item)) skipped += 1;
    else kept.push(item);
  }
  if (!skipped) return "검토 대상으로 반영 완료";
  return skipped === results.length
    ? `새로 반영할 요구사항이 없습니다 · 기존 항목과 중복 ${skipped}건`
    : `검토 대상으로 반영 완료 · 기존 항목과 중복 ${skipped}건 제외`;
}
