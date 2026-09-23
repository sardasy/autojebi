import {render, screen} from "@testing-library/react";
import {expect, it} from "vitest";
import NoticeBrief from "../NoticeBrief";
import type {ServerNoticeBrief} from "@/lib/noticeBrief";

it("renders the exact canonical quotation including whitespace, separately from approval updates", () => {
  const quote = "사업 예산\n   260,000,000원 (부가세 포함)";
  const brief: ServerNoticeBrief = {version: 1, signature: "display", source_signature: "source", submissions: [],
    submission_state: {label: "제출서류", state: "not_detected", items: []}, document_groups: [], warnings: ["다른 페이지 추출 실패"],
    review_comparison: "updated", points: [{label: "예산", state: "found", items: [{text: "normalized summary must not replace quotation", quote,
      documentId: "source", documentName: "공고.hwpx", locator: "section0.xml#xml=0/1", start: 0, end: quote.length, source_sha256: "a".repeat(64)}]}]};
  const view = render(<NoticeBrief documents={[]} prefix="/notices/TEST" serverBrief={brief}/>);
  const paragraph = [...view.container.querySelectorAll("p")].find(p => p.textContent === quote);
  expect(paragraph).toBeDefined();
  expect(screen.getByText("승인 이후 요약 갱신됨 · 원문 승인 유지")).toBeInTheDocument();
  expect(screen.getByText("다른 페이지 추출 실패")).toBeInTheDocument();
  expect(screen.queryByText("normalized summary must not replace quotation")).not.toBeInTheDocument();
});
