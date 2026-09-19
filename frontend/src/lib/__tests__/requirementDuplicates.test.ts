import {describe,expect,it} from "vitest";
import {applyResultMessage,isDuplicateRequirement} from "../requirementDuplicates";

const req = (text:string, quote:string, document_id="source") => ({text,quote,document_id});
describe("requirement duplicate rule shared with the server", () => {
  const existing = [req("납기 확인","납기 90일")];
  it("treats same document with same quote or same text as duplicate", () => {
    expect(isDuplicateRequirement(existing, req("다른 표현","납기 90일"))).toBe(true);
    expect(isDuplicateRequirement(existing, req("납기 확인","다른 인용"))).toBe(true);
    expect(isDuplicateRequirement(existing, req("납기 확인","납기 90일","other"))).toBe(false);
    expect(isDuplicateRequirement(existing, req("새 항목","새 인용"))).toBe(false);
  });
  it("tells the reviewer how many analysis results are skipped", () => {
    expect(applyResultMessage(existing, [req("새 항목","새 인용")])).toBe("검토 대상으로 반영 완료");
    expect(applyResultMessage(existing, [req("다른 표현","납기 90일")])).toBe("새로 반영할 요구사항이 없습니다 · 기존 항목과 중복 1건");
    expect(applyResultMessage(existing, [req("다른 표현","납기 90일"),req("새 항목","새 인용"),req("또 다른 표현","새 인용")]))
      .toBe("검토 대상으로 반영 완료 · 기존 항목과 중복 2건 제외");
    expect(applyResultMessage(existing)).toBe("검토 대상으로 반영 완료");
  });
});
