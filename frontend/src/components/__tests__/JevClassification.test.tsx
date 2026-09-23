import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, expect, it, vi} from "vitest";
import {workspaceApi, type Workspace} from "@/lib/workspace";
import JevClassification from "../workspace/JevClassification";

vi.mock("@/lib/workspace", async importOriginal => ({...await importOriginal<object>(), workspaceApi: vi.fn()}));
const ws = {notice_no: "TEST", version: 3, source_changed: false, jobs: []} as unknown as Workspace;
const base = {visible: true, enabled: true, message: "가상 회사 정책 전송", request_hash: "a".repeat(64),
  policy_version: "test-policy", model: "jev-test", current_job_id: null, history: []};
const mutate = vi.fn();
beforeEach(() => {vi.resetAllMocks();});
const renderPanel = () => render(<JevClassification ws={ws} prefix="/notices/TEST" busy={false} mutate={mutate}/>);

it("requires an explicit click and submits the displayed request identity", async () => {
  vi.mocked(workspaceApi).mockResolvedValue(base);
  renderPanel();
  const button = await screen.findByRole("button", {name: "JEV 분류 실행"});
  expect(mutate).not.toHaveBeenCalled();
  fireEvent.click(button);
  expect(mutate).toHaveBeenCalledWith("/notices/TEST/jobs", expect.objectContaining({kind: "jev", input_version: 3, classification_hash: base.request_hash}), "JEV 분류 접수");
});

it("shows timeout as unevaluated and disables repeat calls", async () => {
  vi.mocked(workspaceApi).mockResolvedValue({...base, current_job_id: "failed", history: [{id: "failed", input_version: 3, status: "failed", result: null, error: {message: "연결 실패"}}]});
  renderPanel();
  expect(await screen.findByRole("button", {name: "JEV 분류 실행"})).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("미평가");
  expect(screen.queryByText("관련 없음")).not.toBeInTheDocument();
});

it("distinguishes historical classifications after an original changes", async () => {
  vi.mocked(workspaceApi).mockResolvedValue({...base, history: [{id: "old", input_version: 2, status: "succeeded", result: null, error: null}]});
  renderPanel();
  expect(await screen.findByText(/현재 원문·정책의 분류 결과가 없습니다/)).toBeVisible();
  expect(screen.getByText(/이전 원문·정책 기준/)).toBeVisible();
  expect(screen.queryByText(/현재 원문·정책 기준/)).not.toBeInTheDocument();
});

it("keeps the feature hidden when disabled", async () => {
  vi.mocked(workspaceApi).mockResolvedValue({...base, visible: false, enabled: false});
  renderPanel();
  await waitFor(() => expect(workspaceApi).toHaveBeenCalled());
  expect(screen.queryByRole("region", {name: "JEV 공고 분류"})).not.toBeInTheDocument();
});
