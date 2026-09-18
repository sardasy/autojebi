import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {workspaceApi} from "@/lib/workspace";
import NoticeFormReview from "../NoticeFormReview";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
const target = {version: 3, output_sha256: "a".repeat(64), unfilled_count: 0, review_status: "pending"};
const props = () => ({prefix: "/notices/FORM", documentId: "form", version: 3, busy: false, onSaved: vi.fn()});
describe("original form human review", () => {
  beforeEach(() => {vi.clearAllMocks(); vi.mocked(workspaceApi).mockResolvedValue(target);});
  it("requires explicit source, content and layout checks and sends the inspected output hash", async () => {
    const p = props(); render(<NoticeFormReview {...p}/>);
    expect(workspaceApi).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name: "작성본 검토 시작"}));
    const approve = await screen.findByRole("button", {name: "양식 검토 승인"});
    expect(approve).toBeDisabled();
    expect(screen.getByRole("link")).toHaveAttribute("href", expect.stringContaining(`version=3&output_sha256=${target.output_sha256}`));
    fireEvent.change(screen.getByLabelText("양식 검토 의견"), {target: {value: "원본 및 실제 배치 대조 완료"}});
    const checks = screen.getAllByRole("checkbox");
    fireEvent.click(checks[0]); fireEvent.click(checks[1]);
    expect(approve).toBeDisabled(); fireEvent.click(checks[2]);
    expect(approve).toBeEnabled();
    const updated = {version: 4}; vi.mocked(workspaceApi).mockResolvedValueOnce(updated);
    fireEvent.click(approve);
    await waitFor(() => expect(p.onSaved).toHaveBeenCalledWith(updated));
    expect(workspaceApi).toHaveBeenLastCalledWith("/notices/FORM/form-fillings/form/review", {
      version: 3, output_sha256: target.output_sha256, approved: true, source_checked: true,
      content_checked: true, layout_checked: true, note: "원본 및 실제 배치 대조 완료",
    });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
  it("blocks incomplete forms but allows rejection and clears checks after a conflict", async () => {
    vi.mocked(workspaceApi).mockResolvedValueOnce({...target, unfilled_count: 1});
    const p = props(); render(<NoticeFormReview {...p}/>);
    fireEvent.click(screen.getByRole("button", {name: "작성본 검토 시작"}));
    await screen.findByLabelText("양식 검토 의견");
    fireEvent.change(screen.getByLabelText("양식 검토 의견"), {target: {value: "빈 항목 작성 필요"}});
    screen.getAllByRole("checkbox").forEach(check => fireEvent.click(check));
    expect(screen.getByRole("button", {name: "양식 검토 승인"})).toBeDisabled();
    vi.mocked(workspaceApi).mockRejectedValueOnce(new Error("작성본이 변경되었습니다"));
    fireEvent.click(screen.getByRole("button", {name: "양식 검토 반려"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("작성본이 변경되었습니다");
    expect(p.onSaved).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(workspaceApi).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({approved: false}));
  });
  it("discards another input version's review target", async () => {
    vi.mocked(workspaceApi).mockResolvedValueOnce({...target, version: 4});
    render(<NoticeFormReview {...props()}/>);
    fireEvent.click(screen.getByRole("button", {name: "작성본 검토 시작"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("입력이 변경");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
