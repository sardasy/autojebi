import type {SourceDocument} from "./workspace";

export interface BriefExcerpt {text: string; documentId: string; documentName: string; quote: string; locator?: string; start?: number; end?: number; source_sha256?: string; member_path?: string[]}
export interface NoticeBriefData {submissions: BriefExcerpt[]; points: {label: string; items: BriefExcerpt[]}[]}
export interface BriefGroup {label: string; items: BriefExcerpt[]; state: "found" | "incomplete" | "not_detected" | "absent_confirmed"; absence?: {created_at: string; actor?: {name: string} | null; scope: {id: string; name: string; sha256: string}[]; note: string} | null}
export interface ServerNoticeBrief extends NoticeBriefData {
  version: number; signature: string; source_signature: string; warnings: string[]; document_groups: string[][];
  points: BriefGroup[]; submission_state: BriefGroup; review_comparison: "none" | "updated" | "unchanged" | "unavailable";
}

const clean = (value: string) => value.replace(/\0/g, " ").replace(/\s+/g, " ").trim();

// HWPX extraction joins every paragraph with a space (kept as is: stored quotes and hashes depend on
// it), so a whole notice can arrive as one line. Re-split only such lines, at the same bullets,
// numbering and sentence ends the loop below flushes on; every piece stays an exact source substring.
const LONG_LINE = 400;
const BREAK = /(?<!\d\.)\s+(?=[①-⑳○※•◇]|\d{1,2}[.)]\s+[가-힣「]|[가나다라마바사아자차카타파하]\.\s)|(?<=[다요][.!])\s+/;
function sourceLines(text: string): {line: string; offset: number}[] {
  const result: {line: string; offset: number}[] = [];
  for (const match of text.matchAll(/[^\r\n]*(?:\r\n|\r|\n|$)/g)) {
    if (!match[0]) continue;
    const line = match[0].replace(/(?:\r\n|\r|\n)$/, "");
    let cursor = 0;
    for (const part of line.length > LONG_LINE ? line.split(BREAK) : [line]) {
      const start = line.indexOf(part, cursor);
      result.push({line: part, offset: match.index! + start});
      cursor = start + part.length;
    }
  }
  return result;
}
const flattened = (text: string) => text.split(/\r?\n/).some(line => line.length > LONG_LINE * 5);

// Keep complete source blocks, including conditions and exceptions. Never use AI paraphrases.
function blocks(text: string): string[] {
  const result: string[] = [];
  let start: number | null = null, end = 0;
  const flush = () => {if (start !== null) result.push(text.slice(start, end)); start = null;};
  for (const {line, offset} of sourceLines(text)) {
    const value = clean(line);
    if (!value || /^\[페이지 \d+\]$/.test(value)) {flush(); continue;}
    if (/^(?:[①-⑳○※•◇-]|\d+[.)]|[가-힣]\.\s)/.test(value)) flush();
    if (/^(?:\d+\.)+$/.test(value) || /^[○◇-]$/.test(value)) continue;
    start ??= offset;
    end = offset + line.length;
    if (/[다요][.!]$/.test(value)) flush();
  }
  flush();
  return result;
}

// HWP table extraction can put each cell on its own line. Only accept the explicit
// submission-table heading and column labels; unrelated numbered tables are not submissions.
function submissionTableBlocks(text: string): string[] {
  const header = /제안서\s*접수\s*시\s*제출\s*자료\s+순번\s+구\s*성\s*내\s*용\s+비\s*고/g;
  const result: string[] = [];
  for (const match of text.matchAll(header)) {
    const tail = text.slice(match.index! + match[0].length);
    const boundary = tail.search(/^\s*(?:※|\[제\s*\d+\s*호\s*서식\])/m);
    if (boundary < 0 || boundary > 20_000) continue;
    const body = tail.slice(0, boundary);
    const rows = [...body.matchAll(/^[ \t]*(\d{1,2})[ \t]*\r?$/gm)];
    if (!rows.length || rows.some((row, index) => Number(row[1]) !== index + 1)) continue;
    for (let i = 0; i < rows.length; i++) {
      const quote = body.slice(rows[i].index, rows[i + 1]?.index ?? body.length).trim();
      if (quote.length <= 2_000) result.push(quote);
    }
  }
  return result;
}

// Preserve label/value whitespace exactly. Colon-free cells are common in HWP;
// read only a value on the same or following line, never infer dates from table order.
function labelledPointBlocks(text: string): string[] {
  const budgetLabels = ["예산금액", "사업예산", "사업금액", "추정가격", "기초금액"];
  const labels = ["납품기한", "계약기간", "과업기한", "수행기간", "용역기간", "제안서 제출기한", "제출 마감일시", ...budgetLabels];
  const result: string[] = [];
  for (const label of labels) {
    const spaced = label.replace(/ /g, "").split("").join("[ \\t]*");
    const pattern = new RegExp(`(?:^|[\\r\\n])[ \\t]*(?:[○◦•-][ \\t]*|\\d{1,2}[.)][ \\t]*)?${spaced}[ \\t]*[:：]?[ \\t]*(?:[\\r\\n]+[ \\t]*)*([^\\r\\n]+)`, "g");
    for (const match of text.matchAll(pattern)) {
      const value = clean(match[1]);
      const valid = budgetLabels.includes(label)
        ? /^(?:[○◦•-]\s*)?금?\s*\d[\d,]*\s*원/.test(value)
        : /(?:\d+[./년]|계약|착수|이내|일까지|별도|공고.*참조)/.test(value);
      if (!valid) continue;
      result.push(match[0].trim());
    }
  }
  return result;
}

export function buildNoticeBrief(documents: SourceDocument[]): NoticeBriefData {
  // File names only suggest candidates. Only complete equal full texts share a display source.
  const sources = new Map<string, SourceDocument>();
  for (const doc of documents.filter(d => d.role === "notice_source" && d.text?.trim())) {
    const complete = doc.extraction?.complete === true && !["partial", "needs_review"].includes(doc.extraction?.table_structure?.status || "") && doc.extraction?.presentation?.status !== "partial";
    const key = complete ? doc.text.normalize("NFC").replace(/\s+/g, " ").trim() : doc.id;
    const old = sources.get(key);
    const nulls = (d: SourceDocument) => d.text.match(/\0/g)?.length || 0;
    if (!old || nulls(doc) < nulls(old) || (nulls(doc) === nulls(old) && flattened(old.text) && !flattened(doc.text))) sources.set(key, doc);
  }
  const all: BriefExcerpt[] = [];
  const seen = new Set<string>();
  const tableSubmissions = new Set<string>();
  for (const doc of [...sources.values()].sort((a,b) => Number(!a.name.includes("공고")) - Number(!b.name.includes("공고")))) {
    const tableQuotes = submissionTableBlocks(doc.text);
    for (const quote of tableQuotes) tableSubmissions.add(`${doc.id}\0${quote}`);
    for (const quote of [...blocks(doc.text), ...tableQuotes, ...labelledPointBlocks(doc.text)]) {
      const text = clean(quote);
      const key = `${doc.id}\0${text}`;
      if (!seen.has(key)) {seen.add(key); all.push({text,quote,documentId:doc.id,documentName:doc.name});}
    }
  }
  const select = (pattern: RegExp) => all.filter(item => pattern.test(item.text));
  const submissions = all.filter(item => {
    if (tableSubmissions.has(`${item.documentId}\0${item.quote}`)) return true;
    const text = item.text.replace(/^(?:\d+[).]|[가-힣]\.)\s*/, "");
    return /^[①-⑳].*(?:\d+\s*부|증명서|확인서|등록증|인감계)/.test(text)
      || /^\d+[.)]\s*/.test(item.text) && /(?:제안서\s*\d+\s*(?:식|부)|(?:등록증|등기부등본|증명서|확인서|인감계).*\d+\s*부|평가\s*참고자료.*제출서류)/.test(text)
      || /^(?:정성|정량(?:적평가)?|기술|가격|요약)\s*제안서\s*[:：(].*(?:식|제출|포함)/.test(text)
      || /^가격입찰서\s*제출$/.test(text)
      || /^(?:제출서류\s*[:：]|입찰서 기타서류.*PDF|제출\s*서류는.*분리)/.test(text);
  });
  return {submissions, points: [
    {label:"제출 일정",items:select(/(?:제출.{0,15}(?:마감|개시|시작|기한)|제출기간)\s*(?:일시)?\s*(?:[:：]|\d{4}[./년])/)},
    {label:"계약·수행 기간",items:all.filter(item => /(?:계약기간|과업기한|납품기한|수행기간|용역기간)(?:[:：]|계약|착수|\d{4}[./년])/.test(item.text.replace(/\s/g, "")))},
    {label:"예산",items:select(/(?:사업예산|사업금액|추정가격|기초금액)\s*[:：]|^(?:\d+[.)]\s*|[○◦•-]\s*)?(?:예산금액|사업예산|사업금액|추정가격|기초금액)\s*(?:[:：]|(?:[○◦•-]\s*)?금?\s*\d[\d,]*\s*원)/)},
    {label:"참가자격",items:select(/(?:확인서를 소지한 자|업종.*등록한|참가자격 제한을 받지|입찰참가자격이 없|입찰에 참가할 수 없)/)},
    {label:"평가 기준",items:select(/(?:평가방법\s*[:：]|종합 평가비율|85%|협상적격자.*선정|협상 적격자.*선정|규격입찰.*적격자\s*\(\s*\d+(?:\.\d+)?\s*점\s*이상\s*\).*(?:선정|개찰)|(?:종합평점|평가결과.*배점).*\d+(?:\.\d+)?\s*점\s*이상.*적격\s*(?:업체|자).*선정)/)},
    {label:"제출 방법·유의사항",items:select(/(?:제출방법\s*[:：]|제안서 제출\s*[:：]|PDF.*(?:형식|용량|MB)|미제출.*무효|하나라도 제출하지|제안서 최종 제출 이후|주민등록번호.*비공개)/)},
  ]};
}
