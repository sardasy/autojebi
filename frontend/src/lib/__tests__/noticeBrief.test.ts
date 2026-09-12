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
});
