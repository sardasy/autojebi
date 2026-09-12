import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import WorkspacePrerequisites, { Prerequisites } from "../WorkspacePrerequisites";
import { workspaceApi } from "@/lib/workspace";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
const result: Prerequisites = {input_version: 5, template_key: "proposal", checked_at: "2026-09-08T09:00:00Z",
  hwp_request_available: false, required_missing: [], mapping_fields: ["company_name"], items: [
    {code: "q", title: "정보통신공사업 0036", state: "blocked", detail: "실제 증빙 확인 필요", target: "documents", action: "자격·증빙 검토", blocks_hwp: false},
    {code: "worker_recovery", title: "HWP Worker · 복구 확인 필요", state: "blocked", detail: "한글 종료 확인 필요", target: "recovery", action: "복구", blocks_hwp: true},
  ]};
const props = {prefix: "/notices/test", version: 5, template: "proposal", onNavigate: vi.fn(), onChecked: vi.fn()};
beforeEach(() => vi.resetAllMocks());

it("checks automatically and links qualification to real review without recovery bypass", async () => {
  vi.mocked(workspaceApi).mockResolvedValue(result);
  render(<WorkspacePrerequisites {...props}/>);
  expect(workspaceApi).toHaveBeenCalledTimes(1);
  expect(await screen.findByText(/정보통신공사업 0036/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "자격·증빙 검토"}));
  expect(props.onNavigate).toHaveBeenCalledWith("documents", undefined);
  expect(screen.getByText("복구 절차 확인")).toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "복구 승인"})).not.toBeInTheDocument();
  expect(props.onChecked).toHaveBeenLastCalledWith(result);
});

it("hides results after input changes and rejects late responses", async () => {
  const resolvers: ((value: Prerequisites) => void)[] = [];
  vi.mocked(workspaceApi).mockImplementation(() => new Promise(r => {resolvers.push(r);}));
  const {rerender} = render(<WorkspacePrerequisites {...props}/>);
  rerender(<WorkspacePrerequisites {...props} version={6}/>);
  resolvers[0](result);
  const latest = {...result, input_version:6};
  resolvers[1](latest);
  await waitFor(()=>expect(props.onChecked).toHaveBeenLastCalledWith(latest));
  expect(props.onChecked).not.toHaveBeenCalledWith(result);
});

it("clears a prior successful check on recheck failure", async () => {
  vi.mocked(workspaceApi).mockResolvedValueOnce(result).mockRejectedValueOnce(new Error("private provider error"));
  render(<WorkspacePrerequisites {...props}/>);
  await screen.findByText(/정보통신공사업 0036/);
  fireEvent.click(screen.getByRole("button", {name: "필수조건 다시 확인"}));
  await waitFor(() => expect(screen.getByLabelText("필수조건 결과")).toHaveTextContent("조회하지 못했습니다"));
  expect(screen.queryByText(/정보통신공사업 0036/)).not.toBeInTheDocument();
  expect(props.onChecked).toHaveBeenLastCalledWith(null);
});

it("refreshes after inspection completion without requiring an input change", async () => {
  vi.mocked(workspaceApi).mockResolvedValue(result);
  const {rerender} = render(<WorkspacePrerequisites {...props} refreshKey="job:running"/>);
  await screen.findByText(/정보통신공사업 0036/);
  rerender(<WorkspacePrerequisites {...props} refreshKey="job:succeeded"/>);
  await waitFor(()=>expect(workspaceApi).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("필수조건 결과").closest("details")).toBeNull();
});
