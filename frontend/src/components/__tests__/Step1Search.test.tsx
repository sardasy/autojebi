import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actionSearchG2B } from "@/lib/actions";
import { Step1Search } from "../Step1Search";
import { ToastProvider } from "../Toast";

vi.mock("@/lib/actions", () => ({ actionSearchG2B: vi.fn(), actionUpsertFromSearchResult: vi.fn() }));

describe("Step1Search", () => {
  it("replaces a previous error immediately while the next request is pending", async () => {
    vi.mocked(actionSearchG2B).mockResolvedValueOnce({ ok: false, error: "연결 시간 초과" });
    render(<ToastProvider><Step1Search /></ToastProvider>);
    fireEvent.change(screen.getByRole("textbox", { name: "G2B 검색어" }), { target: { value: "전자파 해석 SW" } });
    fireEvent.click(screen.getByRole("button", { name: "G2B 라이브 검색" }));
    await waitFor(() => expect(within(screen.getByRole("status")).getByText(/연결 시간 초과/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "G2B 라이브 검색" })).toBeEnabled());
    let finish!: (value: Awaited<ReturnType<typeof actionSearchG2B>>) => void;
    vi.mocked(actionSearchG2B).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "G2B 라이브 검색" }));
    expect(within(screen.getByRole("status")).getByText("G2B 검색 중")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "처리 중…" })).toBeDisabled();
    await act(async () => finish({ ok: true, data: { items: [], total: 0, page: 1, page_size: 30, total_pages: 0 } }));
    expect(within(screen.getByRole("status")).getByText(/검색 결과가 없습니다/)).toBeInTheDocument();
  });
});
