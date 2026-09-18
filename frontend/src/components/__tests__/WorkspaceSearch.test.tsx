import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorkspacesPage from "@/app/workspace/page";
import { workspaceApi } from "@/lib/workspace";
import { deadlineState } from "@/lib/deadline";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
const item = {notice_no: "OPEN", title: "신규 PLECS", org_name: "검증 기관", close_date: "2099-09-14T10:00:00+09:00", already_exists: false, raw: {}};
describe("WorkspaceSearch", () => {
  beforeEach(() => {
    vi.mocked(workspaceApi).mockReset();
    vi.mocked(workspaceApi).mockImplementation(async path => path === "/search" ? {items: [item, {...item, notice_no:"OLD", title:"종료 PLECS", close_date:"2000-01-01T10:00:00+09:00"}, {...item, notice_no:"UNKNOWN", title:"일정 미확인", close_date:null}], total:3} : {items:[], has_more:false});
  });
  it("distinguishes expired, unknown and future deadlines at the exact boundary", () => {
    const now = Date.parse("2026-09-14T01:00:00Z");
    expect(deadlineState("2026-09-14T10:00:00+09:00", now)).toBe("마감");
    expect(deadlineState("2026-09-14T10:00:01+09:00", now)).toBe("마감 전");
    expect(deadlineState(null, now)).toBe("마감 미확인");
    expect(deadlineState("invalid", now)).toBe("마감 미확인");
  });
  it("shows the institution and deadline, hides closed/unknown until requested", async () => {
    render(<WorkspacesPage/>);
    fireEvent.change(screen.getByLabelText("G2B 공고명"), {target:{value:"PLECS"}});
    fireEvent.click(screen.getByRole("button", {name:"G2B 라이브 검색"}));
    await screen.findByText("신규 PLECS");
    expect(screen.getByText(/검증 기관 · OPEN/)).toBeInTheDocument();
    expect(screen.queryByText("종료 PLECS")).not.toBeInTheDocument();
    expect(screen.queryByText("일정 미확인")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("마감 전 공고만"));
    expect(screen.getByText("종료 PLECS")).toBeInTheDocument();
    expect(screen.getByText(/마감 미확인 · 일시 확인 필요/)).toBeInTheDocument();
  });
  it("clears old results when a later search fails", async () => {
    render(<WorkspacesPage/>);
    fireEvent.change(screen.getByLabelText("G2B 공고명"), {target:{value:"PLECS"}});
    fireEvent.click(screen.getByRole("button", {name:"G2B 라이브 검색"}));
    await screen.findByText("신규 PLECS");
    await waitFor(() => expect(screen.getByRole("button", {name:"G2B 라이브 검색"})).toBeEnabled());
    vi.mocked(workspaceApi).mockRejectedValueOnce(new Error("연결 실패"));
    fireEvent.click(screen.getByRole("button", {name:"G2B 라이브 검색"}));
    await screen.findByText("연결 실패");
    expect(screen.queryByText("신규 PLECS")).not.toBeInTheDocument();
  });
  it("records a manually confirmed deadline with an explicit Korean timezone", async () => {
    render(<WorkspacesPage/>);
    fireEvent.change(screen.getByLabelText("공고번호"), {target: {value: "TEST-ONLY"}});
    fireEvent.change(screen.getByLabelText("공고명"), {target: {value: "가상 공고"}});
    fireEvent.change(screen.getByLabelText("공고 기관"), {target: {value: "시험 기관"}});
    fireEvent.change(screen.getByLabelText("입찰 마감일시 (한국시간)"), {target: {value: "2099-10-03T14:30"}});
    fireEvent.submit(screen.getByLabelText("공고번호").closest("form")!);
    await waitFor(() => expect(workspaceApi).toHaveBeenCalledWith("/notices", expect.objectContaining({
      notice_no: "TEST-ONLY", org_name: "시험 기관", close_date: "2099-10-03T14:30:00+09:00",
    })));
  });
});
