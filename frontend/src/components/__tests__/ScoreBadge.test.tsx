import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreBadge } from "../ScoreBadge";

describe("ScoreBadge", () => {
  it("renders dash when value is null", () => {
    render(<ScoreBadge value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("uses emerald color for high score (>= 0.8)", () => {
    const { container } = render(<ScoreBadge value={0.85} />);
    expect(container.querySelector(".bg-emerald-600")).not.toBeNull();
  });

  it("uses amber color for mid score (>= 0.6)", () => {
    const { container } = render(<ScoreBadge value={0.65} />);
    expect(container.querySelector(".bg-amber-500")).not.toBeNull();
  });

  it("uses orange color for low score (>= 0.4)", () => {
    const { container } = render(<ScoreBadge value={0.5} />);
    expect(container.querySelector(".bg-orange-500")).not.toBeNull();
  });

  it("uses red for very low score (> 0)", () => {
    const { container } = render(<ScoreBadge value={0.2} />);
    expect(container.querySelector(".bg-red-700")).not.toBeNull();
  });

  it("supports 0to100 mode and divides by 100", () => {
    const { container } = render(<ScoreBadge value={85} mode="0to100" />);
    // 85/100 = 0.85 → emerald
    expect(container.querySelector(".bg-emerald-600")).not.toBeNull();
    expect(screen.getByText(/85/)).toBeInTheDocument();
  });

  it("renders label prefix when provided", () => {
    render(<ScoreBadge value={0.5} label="종합" />);
    expect(screen.getByText(/종합/)).toBeInTheDocument();
  });
});
