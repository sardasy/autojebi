import {describe,expect,it} from "vitest";
import {buildNoticeBrief} from "../noticeBrief";
import type {SourceDocument} from "../workspace";

const doc = (text:string, name="공고.hwp", id="source"): SourceDocument => ({id,name,text,role:"notice_source",confirmed:false,text_origin:"hwp_ole"});
describe("source-only notice brief", () => {
  it("keeps submission conditions, alternatives, quantities and source identity", () => {
    const text = "4. 제출서류\n① 사업자등록증 사본 1부\n② 법인등기부등본(법인일 경우) 1부, 주민등록등본(개인일 경우) 1부\n③ 사용인감계 1부\n(미등록된 사용인감일 경우 제출)\n\n1) 정성제안서: 제안서 1식(증빙 포함)";
    const value = buildNoticeBrief([doc(text)]);
    expect(value.submissions).toHaveLength(4);
    expect(value.submissions[1].text).toContain("개인일 경우");
    expect(value.submissions[2].text).toContain("미등록된 사용인감일 경우");
    for (const item of value.submissions) {expect(text).toContain(item.quote); expect(item.documentId).toBe("source");}
  });
  it("shows different source deadlines without choosing one or approving them", () => {
    const value = buildNoticeBrief([doc("계약기간: 계약일~2026.11.30."),doc("과업기한 : 계약일로부터 50일 이내","제안요청서.hwp","rfp")]);
    expect(value.points.find(p=>p.label==="계약·수행 기간")?.items).toHaveLength(2);
  });
  it("prefers readable same-name source and excludes company reference", () => {
    const value = buildNoticeBrief([doc("① 사업자등록증\0사본 1부","공고.pdf","pdf"),doc("① 사업자등록증 사본 1부"),{...doc("② 다른 회사 증명서 1부"),role:"company_reference"}]);
    expect(value.submissions).toHaveLength(1);
    expect(value.submissions[0].documentId).toBe("source");
  });
  it("does not fabricate missing sections or infer requirements from filenames", () => {
    const value = buildNoticeBrief([doc("일반 안내\n③ 계약담당공무원은 입찰 공고서에 명시하여야 한다.\n가격입찰서, 제안서 중 어느 하나라도 미제출 시 무효","사업자등록증 제출.pdf")]);
    expect(value.submissions).toEqual([]);
    expect(value.points.find(p=>p.label==="예산")?.items).toEqual([]);
  });
  it("extracts schedule and submission format without removing negation", () => {
    const value = buildNoticeBrief([doc("전자입찰서(가격·제안서) 제출 마감일시: 2026.09.22.(화), 10:00\n\nPDF 파일 형식으로 제출하여야 하며 총 용량은 300MB를 초과할 수 없습니다. (zip 파일 업로드 불가)")]);
    expect(value.points.find(p=>p.label==="제출 일정")?.items[0].text).toContain("10:00");
    expect(value.points.find(p=>p.label==="제출 방법·유의사항")?.items[0].text).toContain("zip 파일 업로드 불가");
  });
  // HWPX extraction has no paragraph breaks: a real 19,486-character notice arrived as one line and
  // every key fact showed the whole document (108,324 characters, 72,045px tall).
  const flat = ["조달물자[물품] 제조 입찰 공고", "이 입찰 설명서는 입찰자와 낙찰자가 숙지하고 준수하여야 할 사항을 기재한 것입니다.".repeat(60),
    "1. 입찰개요 ----------", "○ 입찰공고번호: R26BK01715307-000", "○ 사업금액: 810,000,000 원(부가가치세 포함)", "○ 납품기한: 계약 후 90일 이내",
    "2. 입찰(개찰) 일시 및 장소 ----------", "○ 제안서ㆍ가격 전자입찰서 제출 마감일시: 2026/09/29 10:00", "○ 공고일: 2026. 9. 19. 오전 10:00 게시",
    "◇ 사업예산 및 입찰금액은 부가가치세를 포함한 가격입니다.", "① 사업자등록증 사본 1부", "② 사용인감계 1부 (미등록된 사용인감일 경우 제출)"].join(" ");
  it("splits a single-line HWPX text into bounded, exact excerpts", () => {
    expect(flat).not.toContain("\n");
    const value = buildNoticeBrief([doc(flat,"공고서.hwpx")]);
    const point = (label:string) => value.points.find(p=>p.label===label)?.items || [];
    expect(point("제출 일정").map(i=>i.text)).toEqual(["○ 제안서ㆍ가격 전자입찰서 제출 마감일시: 2026/09/29 10:00"]);
    expect(point("예산").map(i=>i.text)).toEqual(["○ 사업금액: 810,000,000 원(부가가치세 포함)"]);
    expect(point("계약·수행 기간").map(i=>i.text)).toEqual(["○ 납품기한: 계약 후 90일 이내"]);
    expect(value.submissions.map(i=>i.text)).toEqual(["① 사업자등록증 사본 1부","② 사용인감계 1부 (미등록된 사용인감일 경우 제출)"]);
    for (const item of [...value.submissions, ...value.points.flatMap(p=>p.items)]) {expect(flat).toContain(item.quote); expect(item.text.length).toBeLessThan(200);}
  });
  it("does not break spaced dates and leaves ordinary short lines untouched", () => {
    const value = buildNoticeBrief([doc(flat.replace("제출 마감일시: 2026/09/29 10:00","제출 마감일시: 2026. 9. 29. 오전 10:00"),"공고서.hwpx")]);
    expect(value.points.find(p=>p.label==="제출 일정")?.items[0].text).toContain("2026. 9. 29. 오전 10:00");
    const short = "제출 마감일시: 2026.09.22. 10:00 ○ 사업금액: 100원";
    expect(buildNoticeBrief([doc(short)]).points.find(p=>p.label==="제출 일정")?.items[0].text).toBe(short);
  });
  it("prefers the same-name copy that kept its line structure", () => {
    const lined = "○ 사업금액: 810,000,000 원\n○ 납품기한: 계약 후 90일 이내";
    for (const docs of [[doc(flat,"공고서.hwpx","hwpx"),doc(lined,"공고서.pdf","pdf")],[doc(lined,"공고서.pdf","pdf"),doc(flat,"공고서.hwpx","hwpx")]])
      expect(buildNoticeBrief(docs).points.find(p=>p.label==="예산")?.items.map(i=>i.documentId)).toEqual(["pdf"]);
  });
});
