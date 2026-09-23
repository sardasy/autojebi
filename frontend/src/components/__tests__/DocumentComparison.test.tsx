import {fireEvent, render, screen} from "@testing-library/react";
import {expect, it, vi} from "vitest";
import type {Workspace} from "@/lib/workspace";
import DocumentComparison from "../workspace/DocumentComparison";

const base = {version: 2, source_changed: false, kordoc_comparison_enabled: true,
  inputs: {documents: [{id: "source", name: "test.hwpx", role: "notice_source"}]}, jobs: []} as unknown as Workspace;

it("runs only on explicit click and is hidden when disabled", () => {
  const run = vi.fn().mockResolvedValue(undefined);
  const {rerender} = render(<DocumentComparison ws={base} busy={false} run={run}/>);
  expect(run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("문서 추출 비교 · 검증용"));
  fireEvent.click(screen.getByRole("button", {name: "문서 추출 비교 실행"}));
  expect(run).toHaveBeenCalledWith("document_compare");
  rerender(<DocumentComparison ws={{...base, kordoc_comparison_enabled: false}} busy={false} run={run}/>);
  expect(screen.queryByText("문서 추출 비교 · 검증용")).not.toBeInTheDocument();
});

it("marks stale and unpaginated candidates and does not render markup or approval controls", () => {
  const ws: Workspace = {...base, jobs: [{id: "job", kind: "document_compare", input_version: 1, status: "succeeded",
    quality: "warning", error: null, created_at: "2026-09-23T00:00:00Z", finished_at: null,
    result: {engine_version: "4.14.1", comparisons: [{document_id: "source", name: "test.hwpx", input_version: 1, status: "compared",
      baseline_text: "original", comparison: {state: "different", missing_token_count: 1, added_token_count: 1, missing_examples: [], added_examples: []},
      candidate: {text: "<script>danger</script>", page_mode: "section", tables: [], fragments: [], warnings: []}}]}}]};
  render(<DocumentComparison ws={ws} busy={false} run={vi.fn()}/>);
  fireEvent.click(screen.getByText("문서 추출 비교 · 검증용"));
  expect(screen.getByText(/과거 입력 결과/)).toBeVisible();
  expect(screen.getByText(/실제 페이지 번호 미확인/)).toBeVisible();
  expect(screen.getByText("<script>danger</script>")).toBeVisible();
  expect(screen.queryByRole("button", {name: /승인|반영/})).not.toBeInTheDocument();
});
