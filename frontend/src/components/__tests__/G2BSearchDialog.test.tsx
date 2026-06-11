import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { NoticeSearchItem } from "@/lib/api";

import { ToastProvider } from "../Toast";

vi.mock("@/lib/actions", () => ({
  actionSearchG2B: vi.fn(),
  actionUpsertFromSearchResult: vi.fn(),
}));

async function loadDialog() {
  const mod = await import("../G2BSearchDialog");
  return mod.G2BSearchDialog;
}

function makeItem(overrides: Partial<NoticeSearchItem> = {}): NoticeSearchItem {
  return {
    notice_no: "R26X001-000",
    title: "ABB 차단기 22.9kV",
    source: "G2B",
    org_name: "조달청",
    base_price: 10_000_000,
    open_date: "2026-06-01T09:00:00+09:00",
    close_date: "2026-06-15T18:00:00+09:00",
    raw: { bidNtceNo: "R26X001" },
    already_exists: false,
    ...overrides,
  };
}

async function openDialog() {
  const Dialog = await loadDialog();
  render(
    <ToastProvider>
      <Dialog />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: /G2B 라이브 검색/ }));
}

describe("G2BSearchDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders search results from actionSearchG2B", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      data: { items: [makeItem()], total: 1, page: 1, page_size: 50, total_pages: 1 },
    });

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "ABB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(screen.getByText("ABB 차단기 22.9kV")).toBeInTheDocument(),
    );
    expect(screen.getByText("R26X001-000")).toBeInTheDocument();
    expect(screen.getByText(/조달청/)).toBeInTheDocument();
    // 신규 항목 → 저장 버튼
    expect(
      screen.getByRole("button", { name: "저장" }),
    ).toBeInTheDocument();
  });

  it("shows '이미 등록' badge for already_exists items", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      data: {
        items: [makeItem({ already_exists: true })],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      },
    });

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "ABB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(screen.getByText(/이미 등록/)).toBeInTheDocument(),
    );
    // 저장 버튼 없어야 함
    expect(
      screen.queryByRole("button", { name: "저장" }),
    ).not.toBeInTheDocument();
  });

  it("shows 'no results' message when empty", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      data: { items: [], total: 0, page: 1, page_size: 50, total_pages: 0 },
    });

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "없는키워드" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(
        screen.getByText(/G2B 검색 결과가 없습니다/),
      ).toBeInTheDocument(),
    );
  });

  it("rejects empty keyword without calling action", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");

    await openDialog();
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    expect(actionSearchG2B).not.toHaveBeenCalled();
  });

  it("flips row to '이미 등록' after successful save", async () => {
    const { actionSearchG2B, actionUpsertFromSearchResult } = await import(
      "@/lib/actions"
    );
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      data: { items: [makeItem()], total: 1, page: 1, page_size: 50, total_pages: 1 },
    });
    (actionUpsertFromSearchResult as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      { ok: true, data: { notice_no: "R26X001-000" } },
    );

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "ABB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "저장" })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() =>
      expect(screen.getByText(/이미 등록/)).toBeInTheDocument(),
    );
    expect(actionUpsertFromSearchResult).toHaveBeenCalledWith(
      expect.objectContaining({ notice_no: "R26X001-000" }),
    );
  });

  it("keeps save button when upsert fails", async () => {
    const { actionSearchG2B, actionUpsertFromSearchResult } = await import(
      "@/lib/actions"
    );
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      data: { items: [makeItem()], total: 1, page: 1, page_size: 50, total_pages: 1 },
    });
    (actionUpsertFromSearchResult as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      { ok: false, error: "upsert failed" },
    );

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "ABB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "저장" })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    // 실패 후에도 저장 버튼은 다시 활성화되고, 이미 등록 배지는 없어야 함
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "저장" })).not.toBeDisabled(),
    );
    expect(screen.queryByText(/이미 등록/)).not.toBeInTheDocument();
  });

  it("페이지네이션 UI: 총 건수·페이지 정보·다음 버튼 노출", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      data: {
        items: [makeItem()],
        total: 120,
        page: 1,
        page_size: 50,
        total_pages: 3,
      },
    });

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "ABB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(screen.getByText(/총 120건/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/1 \/ 3 페이지/)).toBeInTheDocument();
    // page=1 이므로 "이전" 버튼은 disabled, "다음"은 활성
    expect(screen.getByRole("button", { name: /이전/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /다음/ })).not.toBeDisabled();
  });

  it("'다음' 클릭 시 page=2로 동일 키워드 재검색", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");
    (actionSearchG2B as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [makeItem()],
          total: 120,
          page: 1,
          page_size: 50,
          total_pages: 3,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [makeItem({ notice_no: "R26X051-000", title: "다음 페이지 항목" })],
          total: 120,
          page: 2,
          page_size: 50,
          total_pages: 3,
        },
      });

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "전력" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /다음/ })).not.toBeDisabled(),
    );

    fireEvent.click(screen.getByRole("button", { name: /다음/ }));

    await waitFor(() =>
      expect(screen.getByText(/2 \/ 3 페이지/)).toBeInTheDocument(),
    );
    expect(screen.getByText("다음 페이지 항목")).toBeInTheDocument();

    // 두 번째 호출에 page=2가 전달됐는지
    expect(actionSearchG2B).toHaveBeenCalledTimes(2);
    expect(actionSearchG2B).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ keyword: "전력", page: 2, page_size: 50 }),
    );
  });

  it("surfaces search error via toast and shows no rows", async () => {
    const { actionSearchG2B } = await import("@/lib/actions");
    (actionSearchG2B as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      error: "POST /notices/search failed: 422 search range must not exceed 90 days",
    });

    await openDialog();
    fireEvent.change(screen.getByPlaceholderText(/ABB 차단기/), {
      target: { value: "ABB" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^검색$/ }));

    await waitFor(() =>
      expect(
        screen.getByText(/G2B 검색 실패.*90 days/),
      ).toBeInTheDocument(),
    );
  });
});
