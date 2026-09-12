import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import WorkspaceLlmStatus from "../WorkspaceLlmStatus";
import { workspaceApi } from "@/lib/workspace";

vi.mock("@/lib/workspace", () => ({workspaceApi: vi.fn()}));
beforeEach(() => vi.mocked(workspaceApi).mockReset());

it("shows OpenAI without mislabeling it as Claude", async () => {
  vi.mocked(workspaceApi).mockResolvedValue({llm: {provider:"openai", model:"gpt-4.1-mini", key_registered:false, connection_status:"not_checked"}});
  render(<WorkspaceLlmStatus/>);
  expect(await screen.findByText("OpenAI · gpt-4.1-mini")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("키 미등록 · 분석 실행 불가");
});

it("distinguishes a registered Gemini key from verified connectivity", async () => {
  vi.mocked(workspaceApi).mockResolvedValue({llm: {provider: "gemini", model: "gemini-test", key_registered: true, connection_status: "not_checked"}});
  render(<WorkspaceLlmStatus/>);
  expect(await screen.findByText("Google Gemini · gemini-test")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("실제 연결은 분석 실행 결과에서 확인 필요");
  expect(workspaceApi).toHaveBeenCalledWith("/settings");
});

it("shows missing credentials and refreshes settings without running analysis", async () => {
  vi.mocked(workspaceApi).mockResolvedValue({llm: {provider: "anthropic", model: "claude-test", key_registered: false, connection_status: "not_checked"}});
  render(<WorkspaceLlmStatus/>);
  expect(await screen.findByText("키 미등록 · 분석 실행 불가")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "AI 설정 새로고침"}));
  await waitFor(() => expect(workspaceApi).toHaveBeenCalledTimes(2));
  expect(vi.mocked(workspaceApi).mock.calls.every(([path]) => path === "/settings")).toBe(true);
});

it("does not show private error bodies or stale settings after refresh fails", async () => {
  vi.mocked(workspaceApi).mockResolvedValueOnce({llm: {provider: "gemini", model: "gemini-test", key_registered: true, connection_status: "not_checked"}})
    .mockRejectedValueOnce(new Error("private provider response"));
  render(<WorkspaceLlmStatus/>);
  await screen.findByText("Google Gemini · gemini-test");
  fireEvent.click(screen.getByRole("button", {name: "AI 설정 새로고침"}));
  await screen.findByText("AI 설정을 조회하지 못했습니다. API 연결 후 다시 확인하세요.");
  expect(screen.queryByText(/private provider/)).not.toBeInTheDocument();
  expect(screen.queryByText(/키 등록됨/)).not.toBeInTheDocument();
});
