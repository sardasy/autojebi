import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkspaceSectionReview from "../WorkspaceSectionReview";
import { Workspace } from "@/lib/workspace";

const section = {id: "s", text: "Verified draft", review_status: "approved", evidence_ids: ["d"], requirement_ids: ["r"]};
const ws = {version: 3, source_changed: false, inputs: {documents: [{id: "d", name: "Evidence.pdf", role: "product_evidence", confirmed: true}], requirements: [{id: "r", text: "Delivery"}]}} as Workspace;
describe("document review actions", () => {
  it("shows approved content read-only without an ambiguous approval checkbox", () => {
    render(<WorkspaceSectionReview section={section} ws={ws} prefix="/notices/N" busy={false} note="" mutate={vi.fn()}/>);
    expect(screen.getByLabelText("제안서 섹션 본문")).toHaveAttribute("readonly");
    expect(screen.queryByRole("checkbox", {name: "원문과 사실 확인 완료"})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "수정"}));
    expect(screen.getByLabelText("제안서 섹션 본문")).not.toHaveAttribute("readonly");
  });
  it("saves edits as pending, never as an implicit rejection", () => {
    const mutate = vi.fn();
    render(<WorkspaceSectionReview section={{...section, review_status: "pending"}} ws={ws} prefix="/notices/N" busy={false} note="" mutate={mutate}/>);
    fireEvent.change(screen.getByLabelText("섹션 검토 의견"), {target: {value: "Updated wording"}});
    fireEvent.click(screen.getByRole("button", {name: "초안 저장"}));
    expect(mutate).toHaveBeenCalledWith("/notices/N/sections/s/review", expect.objectContaining({approved: null, version: 3, note: "Updated wording", evidence_ids: ["d"]}), expect.any(String));
  });
  it("requires local review note and sends explicit approval", () => {
    const mutate = vi.fn();
    render(<WorkspaceSectionReview section={{...section, review_status: "pending"}} ws={ws} prefix="/notices/N" busy={false} note="" mutate={mutate}/>);
    expect(screen.getByRole("button", {name: "내용 승인"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("섹션 검토 의견"), {target: {value: "Checked evidence"}});
    fireEvent.click(screen.getByRole("button", {name: "내용 승인"}));
    expect(mutate).toHaveBeenCalledWith("/notices/N/sections/s/review", expect.objectContaining({approved: true}), expect.any(String));
  });
});
