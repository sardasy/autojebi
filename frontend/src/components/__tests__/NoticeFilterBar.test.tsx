import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { ToastProvider } from "../Toast";
import { NoticeFilterBar } from "../NoticeFilterBar";

function renderWithToast(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("NoticeFilterBar", () => {
  it("renders G2B live-search fields by default", () => {
    const { container } = renderWithToast(<NoticeFilterBar />);

    expect(screen.getByText("G2B 실시간 검색")).toBeInTheDocument();
    expect(container.querySelector('input[name="q"]')).toBeInTheDocument();
    expect(screen.getByText("게시일시")).toBeInTheDocument();
    expect(screen.getByText("입찰 마감일시")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "검색" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "초기화" })).toHaveAttribute(
      "href",
      "/notices",
    );
  });

  it("does not render saved-list filters in G2B mode", () => {
    const { container } = renderWithToast(<NoticeFilterBar />);

    expect(container.querySelector('select[name="lifecycle"]')).toBeNull();
    expect(container.querySelector('input[name="status"]')).toBeNull();
    expect(screen.queryByText(/진행 상태/)).not.toBeInTheDocument();
  });

  it("renders saved-list filters when mode is saved", () => {
    const { container } = renderWithToast(<NoticeFilterBar mode="saved" />);

    expect(screen.getByText("저장 공고 업무 큐")).toBeInTheDocument();
    expect(container.querySelector('select[name="lifecycle"]')).not.toBeNull();
    expect(container.querySelector('input[name="status"]')).not.toBeNull();
    for (const label of ["첨부", "서류", "규격", "HWP", "작성"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it("quick period chips are visible in G2B mode", () => {
    renderWithToast(<NoticeFilterBar />);
    for (const label of ["전체", "당일", "1주일", "1개월", "6개월", "1년"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "2년" })).not.toBeInTheDocument();
  });

  it("serializes open date range when open-date mode is selected", async () => {
    const user = userEvent.setup();
    const { container } = renderWithToast(
      <NoticeFilterBar open_from="2026-05-01" open_to="2026-06-01" />,
    );

    const openRadio = container.querySelector(
      'input[type="radio"][aria-label="게시일시 기준"]',
    ) as HTMLInputElement | null;
    expect(openRadio?.checked).toBe(true);
    expect(container.querySelector('input[name="open_from"]')).not.toBeNull();
    expect(container.querySelector('input[name="close_from"]')).toBeNull();

    const closeRadio = container.querySelector(
      'input[type="radio"][aria-label="입찰 마감일시 기준"]',
    ) as HTMLInputElement | null;
    expect(closeRadio).not.toBeNull();
    await user.click(closeRadio!);

    expect(container.querySelector('input[name="close_from"]')).not.toBeNull();
    expect(container.querySelector('input[name="open_from"]')).toBeNull();
  });

  it("keeps page_size in the submitted form", () => {
    const { container } = renderWithToast(<NoticeFilterBar page_size="50" />);
    const pageSize = container.querySelector(
      'select[name="page_size"]',
    ) as HTMLSelectElement | null;

    expect(pageSize).not.toBeNull();
    expect(pageSize?.value).toBe("50");
  });
});
