import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricCard } from "../MetricCard";

describe("MetricCard", () => {
  it("renders label", () => {
    render(<MetricCard label="사양" value={0.5} />);
    expect(screen.getByText("사양")).toBeInTheDocument();
  });

  it("shows '—' when value is null", () => {
    render(<MetricCard label="자격" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats value to 2 decimals", () => {
    render(<MetricCard label="예가" value={0.7345} />);
    expect(screen.getByText("0.73")).toBeInTheDocument();
  });

  it("uses emerald text color for >= 0.8", () => {
    const { container } = render(<MetricCard label="종합" value={0.9} />);
    expect(container.querySelector(".text-emerald-400")).not.toBeNull();
  });

  it("renders hint when provided", () => {
    render(<MetricCard label="x" value={0.5} hint="설명" />);
    expect(screen.getByText("설명")).toBeInTheDocument();
  });
});
