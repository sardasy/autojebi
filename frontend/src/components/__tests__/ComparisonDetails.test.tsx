import {render, screen} from "@testing-library/react";
import {expect, it} from "vitest";
import {comparisonTitle, type ComparisonV2} from "@/lib/documentComparison";
import {codepointSlice} from "@/lib/textOffsets";
import ComparisonDetails from "../workspace/ComparisonDetails";

const base: ComparisonV2 = {
  comparison_version: 2, offset_unit: "unicode_codepoint", offset_basis: "comparison_text",
  basis: "legacy_extraction", has_baseline: true, completion: "complete",
  before_text: "😀 200 이상", after_text: "😀 220 이하", changes: [], controls: [], tables: [],
  summary: {content: 0, whitespace: 0, unclassified: 0, control_groups: 23,
    changed_cells: 0, unmatched_tables: 0, structure_changes: 0, cells_not_compared: false},
};

it("only declares no body change when comparison completed without content or unknown changes", () => {
  expect(comparisonTitle(base)).toBe("본문 내용 차이 없음");
  for (const changed of [
    {...base, completion: "truncated" as const},
    {...base, summary: {...base.summary, content: 1}},
    {...base, summary: {...base.summary, unclassified: 1}},
  ]) expect(comparisonTitle(changed)).not.toContain("본문 내용 차이 없음");
  expect(comparisonTitle({...base, summary: {...base.summary, changed_cells: 1}})).toContain("표 1셀 변경");
  expect(comparisonTitle({...base, summary: {...base.summary, unmatched_tables: 2}})).toContain("표 2개 구조 대응 확인 필요");
  expect(comparisonTitle({...base, summary: {...base.summary, cells_not_compared: true}})).toContain("표 셀 미비교");
});

it("highlights codepoint ranges after emoji with visible deletion and insertion markers", () => {
  const change = {kind: "content" as const, before_start: 2, before_end: 5, after_start: 2,
    after_end: 5, before: "200", after: "220", before_context: "😀 ", after_context: " 이하"};
  const {container} = render(<ComparisonDetails value={{...base, changes: [change], summary: {...base.summary, content: 1}}}/>);
  expect(container.querySelector("del")).toHaveTextContent("[- 200]");
  expect(container.querySelector("ins")).toHaveTextContent("[+ 220]");
  expect(codepointSlice("😀A😀B", 2, 3)).toBe("😀");
  expect(screen.getByText("내부 제어문 23묶음", {selector: "summary"}).parentElement).not.toHaveAttribute("open");
});

it("expands unknown changes by default and exposes incomplete comparison", () => {
  render(<ComparisonDetails value={{...base, completion: "truncated", summary: {...base.summary, unclassified: 1}}}/>);
  expect(screen.getByText("분류 미확인 · 원문 대조 필요").parentElement).toHaveAttribute("open");
  expect(screen.getByRole("alert")).toHaveTextContent("전체 비교 미완료");
  expect(screen.getByRole("status")).not.toHaveTextContent("본문 내용 차이 없음");
});
