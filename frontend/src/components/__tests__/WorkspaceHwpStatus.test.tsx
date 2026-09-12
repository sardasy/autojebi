import {render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import WorkspaceHwpStatus from "../WorkspaceHwpStatus";
import {workspaceApi} from "@/lib/workspace";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
beforeEach(() => vi.resetAllMocks());
describe("WorkspaceHwpStatus", () => {
  it("shows an active stage instead of just connected", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({code:"worker_running", operation:{stage:"table", elapsed_seconds:12}});
    render(<WorkspaceHwpStatus/>);
    await waitFor(() => expect(screen.getByRole("status", {name:"HWP Worker 상태"})).toHaveTextContent("작업 중"));
    expect(screen.getByText("표 작성 · 12초")).toBeInTheDocument();
  });
  it("keeps recovery separate from healthy connectivity", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({code:"worker_recovery", operation:{stage:"save", elapsed_seconds:110}});
    render(<WorkspaceHwpStatus/>);
    await waitFor(() => expect(screen.getByRole("status", {name:"HWP Worker 상태"})).toHaveTextContent("복구 필요"));
    expect(screen.getByText(/추가 실행은 차단됩니다/)).toBeInTheDocument();
  });
});
