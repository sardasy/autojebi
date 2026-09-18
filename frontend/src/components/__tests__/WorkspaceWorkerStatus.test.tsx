import {render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import WorkspaceWorkerStatus from "../WorkspaceWorkerStatus";
import {workspaceApi} from "@/lib/workspace";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
beforeEach(() => vi.resetAllMocks());

const code = {loaded_fingerprint: "a".repeat(64), disk_fingerprint: "b".repeat(64), status: "mismatch", restart_required: true};

describe("WorkspaceWorkerStatus", () => {
  it("keeps a running worker visible and identifies the process needing restart", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({available: true, state: "executing", heartbeat_at: null, last_failure: null,
      runtime: {api: code, workers: {local: code}, status: "mismatch", restart_required: true,
        diagnostics: [{component: "api", code: "code_changed", restart_required: true}, {component: "worker:local", code: "code_changed", restart_required: true}]}});
    render(<WorkspaceWorkerStatus/>);
    await waitFor(() => expect(screen.getByText("작업 실행기 · 실행 중")).toBeInTheDocument());
    expect(screen.getByText("API · 코드 변경 반영을 위한 재시작 필요")).toBeInTheDocument();
    expect(screen.getByText("로컬 문서 실행기 · 코드 변경 반영을 위한 재시작 필요")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("진행 중인 작업이 끝난 뒤");
    expect(screen.queryByText(/접수된 작업은 보존됩니다/)).not.toBeInTheDocument();
  });

  it("does not mistake an older versionless worker for a current build", async () => {
    vi.mocked(workspaceApi).mockResolvedValue({available: true, state: "idle", heartbeat_at: null, last_failure: null,
      runtime: {api: {...code, status: "current", restart_required: false}, workers: {}, status: "unknown", restart_required: false,
        diagnostics: [{component: "worker:external", code: "version_unknown", restart_required: false}]}});
    render(<WorkspaceWorkerStatus/>);
    await waitFor(() => expect(screen.getByText("외부 연동 실행기 · 실행 코드 버전 확인 필요")).toBeInTheDocument());
    expect(screen.queryByText(/진행 중인 작업이 끝난 뒤/)).not.toBeInTheDocument();
  });
});
