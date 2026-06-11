import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../Toast";
import { NoticeFilterBar } from "../NoticeFilterBar";

vi.mock("@/lib/actions", () => ({
  actionCollect: vi.fn().mockResolvedValue({ fetched: 0, new: 0, skipped: 0 }),
}));

const defaultProps = {};

function renderWithToast(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("NoticeFilterBar (KJEBI 스타일)", () => {
  it("상단 항상-보이는 영역 라벨이 노출된다", () => {
    renderWithToast(<NoticeFilterBar {...defaultProps} />);
    expect(screen.getByText("검색 필터")).toBeInTheDocument();
    expect(screen.getByText(/간편검색/)).toBeInTheDocument();
    expect(screen.getByText("게시일시")).toBeInTheDocument();
    expect(screen.getByText("입찰 마감일시")).toBeInTheDocument();
    expect(screen.getByText(/입찰 마감 제외/)).toBeInTheDocument();
  });

  it("간편검색 input과 검색 버튼이 있다", () => {
    const { container } = renderWithToast(<NoticeFilterBar {...defaultProps} />);
    expect(container.querySelector('input[name="q"]')).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "검색" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "초기화" })).toBeInTheDocument();
  });

  it("빠른 기간 칩 7개가 노출된다", () => {
    renderWithToast(<NoticeFilterBar {...defaultProps} />);
    const labels = ["전체", "당일", "1주일", "1개월", "6개월", "1년", "2년"];
    for (const label of labels) {
      expect(
        screen.getByRole("button", { name: label }),
        `chip "${label}" should exist`,
      ).toBeInTheDocument();
    }
  });

  it("기본 lifecycle은 active (마감 제외 ON) — hidden input으로 직렬화", () => {
    const { container } = renderWithToast(<NoticeFilterBar {...defaultProps} />);
    const lifecycle = container.querySelector(
      'input[name="lifecycle"]',
    ) as HTMLInputElement | null;
    expect(lifecycle).not.toBeNull();
    expect(lifecycle?.value).toBe("active");
  });

  it("고급 필터 펼침 토글 — 기본 접힘, 클릭 시 펼침", async () => {
    const user = userEvent.setup();
    const { container } = renderWithToast(<NoticeFilterBar {...defaultProps} />);
    const toggle = screen.getByRole("button", { name: /고급 필터/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const adv = container.querySelector("#filter-advanced");
    expect(adv).not.toBeNull();
    expect(adv?.hasAttribute("hidden")).toBe(true);
    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(adv?.hasAttribute("hidden")).toBe(false);
  });

  it("고급 필터 input들이 DOM에는 항상 존재 (hidden 속성으로만 숨김)", () => {
    const { container } = renderWithToast(<NoticeFilterBar {...defaultProps} />);
    // 단일 input/select은 항상 [name]으로 DOM에 있음
    const alwaysNamed = [
      "org_name",
      "assignee",
      "min_base_price",
      "max_base_price",
      "min_fit_score",
      "max_fit_score",
      "min_score_total",
      "max_score_total",
      "has_grade",
      "has_documents",
      "has_uploads",
      "ready_for_submission",
      "sort",
      "direction",
      "page_size",
    ];
    for (const name of alwaysNamed) {
      expect(
        container.querySelector(`[name="${name}"]`),
        `field "${name}" should be in DOM`,
      ).not.toBeNull();
    }
    // 다중 선택은 MultiSelectChips — 선택되기 전엔 hidden input 미렌더, 옵션 라벨로 존재 확인
    const groupLabels = ["카테고리", "공고유형", "출처", "진행상태"];
    for (const label of groupLabels) {
      expect(
        screen.getByText(label),
        `group label "${label}" should be rendered`,
      ).toBeInTheDocument();
    }
  });

  it("MultiSelectChips는 선택된 항목만 hidden input으로 직렬화", () => {
    const { container } = renderWithToast(
      <NoticeFilterBar category={["HIL", "SW"]} bid_type={["용역"]} />,
    );
    const categoryInputs = container.querySelectorAll('input[name="category"]');
    expect(categoryInputs).toHaveLength(2);
    const values = Array.from(categoryInputs).map(
      (el) => (el as HTMLInputElement).value,
    );
    expect(values).toEqual(expect.arrayContaining(["HIL", "SW"]));

    const bidTypeInputs = container.querySelectorAll('input[name="bid_type"]');
    expect(bidTypeInputs).toHaveLength(1);
    expect((bidTypeInputs[0] as HTMLInputElement).value).toBe("용역");
  });

  it("open_from props가 있으면 라디오 초기값이 게시일시", () => {
    const { container } = renderWithToast(
      <NoticeFilterBar open_from="2026-05-01" open_to="2026-06-01" />,
    );
    // 게시일시 라디오가 checked
    const openRadio = container.querySelector(
      'input[type="radio"][aria-label="게시일시 기준"]',
    ) as HTMLInputElement | null;
    expect(openRadio?.checked).toBe(true);
    // hidden input 이름이 open_from / open_to
    expect(container.querySelector('input[name="open_from"]')).not.toBeNull();
    expect(container.querySelector('input[name="close_from"]')).toBeNull();
  });

  it("close_from props만 있으면 라디오는 입찰 마감일시 (기본)", () => {
    const { container } = renderWithToast(
      <NoticeFilterBar close_from="2026-05-01" close_to="2026-06-01" />,
    );
    const closeRadio = container.querySelector(
      'input[type="radio"][aria-label="입찰 마감일시 기준"]',
    ) as HTMLInputElement | null;
    expect(closeRadio?.checked).toBe(true);
    expect(container.querySelector('input[name="close_from"]')).not.toBeNull();
    expect(container.querySelector('input[name="open_from"]')).toBeNull();
  });

  it("마감 제외 토글 클릭 시 lifecycle hidden input이 all로 바뀐다", async () => {
    const user = userEvent.setup();
    const { container } = renderWithToast(<NoticeFilterBar {...defaultProps} />);
    let lifecycle = container.querySelector(
      'input[name="lifecycle"]',
    ) as HTMLInputElement | null;
    expect(lifecycle?.value).toBe("active");

    const toggle = screen.getByRole("switch", {
      name: "입찰 마감 제외 토글",
    });
    await user.click(toggle);

    lifecycle = container.querySelector(
      'input[name="lifecycle"]',
    ) as HTMLInputElement | null;
    expect(lifecycle?.value).toBe("all");
  });
});
