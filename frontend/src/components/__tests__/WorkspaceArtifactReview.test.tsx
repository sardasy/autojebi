import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {WorkspaceJob} from "@/lib/workspace";
import {TemplateProvenance, templateLabel} from "@/lib/templateProvenance";
import WorkspaceArtifactReview from "../WorkspaceArtifactReview";

const job: WorkspaceJob = {id: "hwp", kind: "hwp", input_version: 5, status: "succeeded", quality: "warning",
  result: {artifact: "draft.hwp", sha256: "a".repeat(64), verified: true, required_missing: [], remaining_placeholders: []},
  error: null, created_at: "2026-09-13", finished_at: "2026-09-13"};
const props = () => ({job, version: 5, sourceChanged: false, busy: false, note: "실파일 대조", onNote: vi.fn(), onReview: vi.fn()});

describe("generated HWP review", () => {
  it("requires layout confirmation and sends the exact generated hash", () => {
    const p = props(); render(<WorkspaceArtifactReview {...p}/>);
    const approve = screen.getByRole("button", {name: "초안 승인"});
    expect(approve).toBeDisabled(); fireEvent.click(screen.getByRole("checkbox"));
    expect(approve).toBeEnabled(); fireEvent.click(approve);
    expect(p.onReview).toHaveBeenCalledWith("approved", {output_sha256: "a".repeat(64), layout_confirmed: true});
  });
  it.each([{verified: false}, {remaining_placeholders: ["name"]}, {sha256: undefined}, {required_missing: ["body"]}])("blocks incomplete HWP approval %j while permitting rejection", result => {
    const p = {...props(), job: {...job, result: {...job.result, ...result}}}; render(<WorkspaceArtifactReview {...p}/>);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", {name: "초안 승인"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button", {name: "반려"}));
    expect(p.onReview).toHaveBeenCalledWith("rejected", expect.anything());
  });
  it("blocks outdated input even after a layout check", () => {
    render(<WorkspaceArtifactReview {...props()} version={6}/>);
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByRole("button", {name: "초안 승인"})).toBeDisabled();
    expect(screen.getByRole("button", {name: "반려"})).toBeDisabled();
  });
  it("blocks validation skeleton approval after visual confirmation and still permits rejection", () => {
    const provenance: TemplateProvenance = {state: "validation_only", template_key: "renamed", template_path: "test.hwp",
      template_sha256: "b".repeat(64), metadata_sha256: null, content_record_sha256: "c".repeat(64),
      generation_allowed: true, approval_allowed: false, warning: "검증 전용 골격입니다. 제출용 출력 승인 불가"};
    const p = {...props(), job: {...job, result: {...job.result, template_provenance: provenance}}};
    render(<WorkspaceArtifactReview {...p}/>);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText(/검증 전용 골격입니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "초안 승인"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button", {name: "반려"}));
    expect(p.onReview).toHaveBeenCalledWith("rejected", expect.anything());
    expect(templateLabel({template_key: "renamed", name: "한글", provenance})).toContain("검증 전용 골격");
    expect(templateLabel({template_key: "bid_form", name: "한글", provenance: {...provenance,
      state: "reviewed_source", approval_allowed: true, warning: null}})).toContain("원본 출처 확인됨");
  });
  it("blocks a legacy default template without a provenance record", () => {
    render(<WorkspaceArtifactReview {...props()} job={{...job, parameters: {template_key: "bid_form"}}}/>);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText(/기본 템플릿의 출처 기록이 없어/)).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "초안 승인"})).toBeDisabled();
  });
});
