import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HwpJobs } from "../DocumentPreparationPanel";
import { ToastProvider } from "../Toast";
import type { ExportRecord, HwpJobRecord } from "@/lib/api";
import { actionReviewHwpJob } from "@/lib/actions";

vi.mock("@/lib/actions", () => ({ actionReviewHwpJob: vi.fn().mockResolvedValue({}) }));
const job: HwpJobRecord = { id: 7, notice_no: "UX-1", export_id: 3, status: "completed", review_status: "pending", input_values: {}, replaced: [], missing: [], remaining_placeholders: ["주소"] };
const file: ExportRecord = { id: 3, kind: "bid_form_hwp", draft_id: "bid_form", output_path: "mock.hwp", mime: "application/x-hwp", generated_at: "2026-09-06T00:00:00Z", validation_status: "warning" };
describe("HWP review safeguards", () => {
  it("requires an opinion for warning approval but permits downloading", async () => {
    render(<ToastProvider><HwpJobs noticeNo="UX-1" jobs={[job]} exports={[file]}/></ToastProvider>);
    expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
    expect(screen.getByRole("link", { name: /파일 다운로드/ })).toHaveAttribute("href", "/api/notices/UX-1/documents/exports/by-id/3/download");
    fireEvent.change(screen.getByRole("textbox", { name: /검토 의견/ }), { target: { value: "주소 수동 확인" } });
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    await waitFor(() => expect(actionReviewHwpJob).toHaveBeenCalledWith("UX-1", 7, { review_status: "approved", review_note: "주소 수동 확인" }));
  });
  it("never enables approval for a failed job", () => {
    render(<ToastProvider><HwpJobs noticeNo="UX-1" jobs={[{...job, status:"failed"}]} exports={[file]}/></ToastProvider>);
    fireEvent.change(screen.getByRole("textbox", { name: /검토 의견/ }), { target: { value: "확인" } });
    expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
    expect(screen.getByText(/생성 실패로 승인할 수 없습니다/)).toBeInTheDocument();
  });
});
