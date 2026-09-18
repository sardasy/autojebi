import type {SourceDocument} from "./workspace";

export interface BriefExcerpt {text: string; documentId: string; documentName: string; quote: string}
export interface NoticeBriefData {submissions: BriefExcerpt[]; points: {label: string; items: BriefExcerpt[]}[]}

const clean = (value: string) => value.replace(/\0/g, " ").replace(/\s+/g, " ").trim();

// Keep complete source blocks, including conditions and exceptions. Never use AI paraphrases.
function blocks(text: string): string[] {
  const result: string[] = [];
  let current: string[] = [];
  const flush = () => {if (current.length) result.push(current.join("\n")); current = [];};
  for (const line of text.split(/\r?\n/)) {
    const value = clean(line);
    if (!value || /^\[페이지 \d+\]$/.test(value)) {flush(); continue;}
    if (/^(?:[①-⑳○※•◇-]|\d+[.)]|[가-힣]\.\s)/.test(value)) flush();
    if (/^(?:\d+\.)+$/.test(value) || /^[○◇-]$/.test(value)) continue;
    current.push(line);
    if (/[다요][.!]$/.test(value)) flush();
  }
  flush();
  return result;
}

export function buildNoticeBrief(documents: SourceDocument[]): NoticeBriefData {
  // Same-named HWP/PDF copies share a display source; keep differently named documents.
  const sources = new Map<string, SourceDocument>();
  for (const doc of documents.filter(d => d.role === "notice_source" && d.text?.trim())) {
    const key = doc.name.replace(/\.(pdf|hwpx?|txt)$/i, "");
    const old = sources.get(key);
    if (!old || (doc.text.match(/\0/g)?.length || 0) < (old.text.match(/\0/g)?.length || 0)) sources.set(key, doc);
  }
  const all: BriefExcerpt[] = [];
  const seen = new Set<string>();
  for (const doc of [...sources.values()].sort((a,b) => Number(!a.name.includes("공고")) - Number(!b.name.includes("공고")))) {
    for (const quote of blocks(doc.text)) {
      const text = clean(quote);
      const key = text.replace(/\s/g, "");
      if (!seen.has(key)) {seen.add(key); all.push({text,quote,documentId:doc.id,documentName:doc.name});}
    }
  }
  const select = (pattern: RegExp) => all.filter(item => pattern.test(item.text));
  const submissions = all.filter(item => {
    const text = item.text.replace(/^(?:\d+[).]|[가-힣]\.)\s*/, "");
    return /^[①-⑳].*(?:\d+\s*부|증명서|확인서|등록증|인감계)/.test(text)
      || /^(?:정성|정량(?:적평가)?|기술|가격|요약)\s*제안서\s*[:：(].*(?:식|제출|포함)/.test(text)
      || /^가격입찰서\s*제출$/.test(text)
      || /^(?:제출서류\s*[:：]|입찰서 기타서류.*PDF|제출\s*서류는.*분리)/.test(text);
  });
  return {submissions, points: [
    {label:"제출 일정",items:select(/(?:제출.{0,15}(?:마감|개시|시작|기한)|제출기간)\s*(?:일시)?\s*[:：]/)},
    {label:"계약·수행 기간",items:select(/(?:계약기간|과업기한|납품기한|수행기간|용역기간)\s*[:：]/)},
    {label:"예산",items:select(/(?:사업예산|사업금액|추정가격|기초금액)\s*[:：]/)},
    {label:"참가자격",items:select(/(?:확인서를 소지한 자|업종.*등록한|참가자격 제한을 받지|입찰참가자격이 없|입찰에 참가할 수 없)/)},
    {label:"평가 기준",items:select(/(?:평가방법\s*[:：]|종합 평가비율|85%|협상적격자.*선정|협상 적격자.*선정)/)},
    {label:"제출 방법·유의사항",items:select(/(?:제출방법\s*[:：]|제안서 제출\s*[:：]|PDF.*(?:형식|용량|MB)|미제출.*무효|하나라도 제출하지|제안서 최종 제출 이후|주민등록번호.*비공개)/)},
  ]};
}
