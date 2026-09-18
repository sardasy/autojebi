import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {WorkspaceJob} from "@/lib/workspace";
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
});
