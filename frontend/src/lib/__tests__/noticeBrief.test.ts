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
  it("keeps incomplete same-name sources separate and excludes company reference", () => {
    const value = buildNoticeBrief([doc("① 사업자등록증\0사본 1부","공고.pdf","pdf"),doc("① 사업자등록증 사본 1부"),{...doc("② 다른 회사 증명서 1부"),role:"company_reference"}]);
    expect(value.submissions).toHaveLength(2);
    expect(value.submissions.map(i => i.documentId)).toEqual(["pdf", "source"]);
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
  it("never hides distinct content just because filenames have the same stem", () => {
    const lined = "○ 사업금액: 810,000,000 원\n○ 납품기한: 계약 후 90일 이내";
    for (const docs of [[doc(flat,"공고서.hwpx","hwpx"),doc(lined,"공고서.pdf","pdf")],[doc(lined,"공고서.pdf","pdf"),doc(flat,"공고서.hwpx","hwpx")]])
      expect(buildNoticeBrief(docs).points.find(p=>p.label==="예산")?.items.map(i=>i.documentId).sort()).toEqual(["hwpx", "pdf"]);
  });
  it("reads Arabic-numbered proposal submissions and keeps conditional alternatives", () => {
    const text = "나. 제안서 제출 서류\n\n1. 제안서 2식\n\n2. 평가 참고자료 등 제안 관련 제출서류\n\n3. 출력한 경쟁입찰참가자격등록증 2부.\n\n4. 법인 등기부등본(개인사업자인 경우 사업자등록증) 2부.";
    const value = buildNoticeBrief([doc(text)]);
    expect(value.submissions).toHaveLength(4);
    expect(value.submissions[3].text).toContain("개인사업자인 경우 사업자등록증");
    for (const item of value.submissions) expect(text).toContain(item.quote);
  });
  it("keeps exact rows and conditions from an explicitly headed HWP submission table", () => {
    const text = "2. 제안서 접수 시 제출 자료\r\n\r\n순번\r\n\r\n구 성 내 용\r\n\r\n비 고\r\n\r\n1\r\n\r\n사업자 등록증\r\n\r\n2부\r\n\r\n2\r\n\r\n사용인감계(증명인감이 아닐 때)\r\n\r\n1부\r\n\r\n3\r\n\r\n신용평가등급확인서\r\n\r\n[주] 확인되지 않으면 평가에서 제외한다.\r\n\r\n1부\r\n\r\n※ 원문 확인 필요";
    const items = buildNoticeBrief([doc(text)]).submissions;
    expect(items).toHaveLength(3);
    expect(items[1].text).toContain("증명인감이 아닐 때");
    expect(items[2].text).toContain("확인되지 않으면 평가에서 제외한다.");
    for (const item of items) expect(text).toContain(item.quote);
    expect(buildNoticeBrief([doc("일반 순번표\n1\n사업자 등록증\n2부\n※ 안내")]).submissions).toEqual([]);
  });
  it("reads colon-free label and value cells without choosing between source deadlines", () => {
    const text = "납품기한\r\n\r\n계약일로부터 45일 이내\r\n\r\n제안서 제출기한\r\n\r\n2099.04.18.(토) 11:00\r\n\r\n제안서 기술평가\r\n\r\n추후 안내";
    const other = "◦ 납품기한 : 계약 후 2개월 이내";
    const value = buildNoticeBrief([doc(text), doc(other, "요청서.hwp", "rfp")]);
    expect(value.points.find(p=>p.label==="계약·수행 기간")?.items).toHaveLength(2);
    const schedule = value.points.find(p=>p.label==="제출 일정")?.items;
    expect(schedule).toHaveLength(1);
    expect(schedule![0].text).toBe("제안서 제출기한 2099.04.18.(토) 11:00");
    expect(text).toContain(schedule![0].quote);
    expect(buildNoticeBrief([doc("제안서 제출기한\n\n제안서 기술평가\n\n추후 안내")]).points.find(p=>p.label==="제출 일정")?.items).toEqual([]);
  });
  it.each(["\r\n", "\r\r\n", "\r"])("preserves the original %j line endings in every quote", separator => {
    const text = ["제안서 제출기한", "2099.04.18. 11:00", "", "① 사용인감계 2부", "(등록되지 않은 경우에만 제출)"].join(separator);
    const value = buildNoticeBrief([doc(text)]);
    expect(value.submissions).toHaveLength(1);
    expect(value.points.find(p=>p.label==="제출 일정")?.items.length).toBeGreaterThan(0);
    for (const item of [...value.submissions, ...value.points.flatMap(p=>p.items)]) expect(text).toContain(item.quote);
  });
  it("reads budget label/value cells with a currency prefix and keeps tax conditions", () => {
    const notice = "예산금액\r\n금12,345원 ※ 부가가치세 포함\r\n\r\n입찰방법\r\n전자입찰";
    const rfp = "4. 사업예산\r\n  ◦ 67,890원(부가가치세 별도)\r\n\r\n5. 납품기한";
    const value = buildNoticeBrief([doc(notice),doc(rfp,"시험요청서.hwp","rfp")]);
    const items = value.points.find(p=>p.label==="예산")!.items;
    expect(items.map(i=>i.text)).toEqual(["예산금액 금12,345원 ※ 부가가치세 포함", "4. 사업예산 ◦ 67,890원(부가가치세 별도)"]);
    for (const item of items) expect(item.documentId === "source" ? notice : rfp).toContain(item.quote);
    const absent = buildNoticeBrief([doc("예산금액\n추후 안내\n\n개찰 결과 기초금액과 상이하면 개찰을 무효로 합니다.")]);
    expect(absent.points.find(p=>p.label==="예산")!.items).toEqual([]);
  });
  it("shows explicit qualification score thresholds without rewriting the threshold or conditions", () => {
    const text = "가. 규격입찰을 개찰한 결과 적격자(73점 이상)로 확정된 자에 한해 가격 입찰 개찰하여\r\n낙찰자를 선정합니다.\r\n\r\n◦ 제출된 제안서를 평가하여 종합평점이 100점 만점에 76.5점 이상을 득한 업체를 규격입찰 적격업체로 선정한다.\r\n\r\n② 평가결과 배점(100점)의 74점 이상을 득한 업체를 규격입찰 적격 업체로 선정\r\n(서류가 허위인 경우는 제외)\r\n③ 다음 항목";
    const items = buildNoticeBrief([doc(text)]).points.find(p=>p.label==="평가 기준")!.items;
    expect(items).toHaveLength(3);
    expect(items[0].text).toContain("적격자(73점 이상)로 확정된 자에 한해");
    expect(items[1].text).toContain("76.5점 이상");
    expect(items[2].text).toContain("서류가 허위인 경우는 제외");
    for (const item of items) expect(text).toContain(item.quote);
    expect(buildNoticeBrief([doc("제안서 기술평가\n수요부서에서 결정\n\n일반 만족도는 74점 이상입니다.")]).points.find(p=>p.label==="평가 기준")!.items).toEqual([]);
  });
});
