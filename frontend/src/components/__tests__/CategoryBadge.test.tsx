import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryBadge } from "../CategoryBadge";

describe("CategoryBadge", () => {
  it.each(["HIL", "SW", "IGBT", "SCR", "수동소자", "ABB장비", "혼합", "비관련"])(
    "renders %s value",
    (val) => {
      render(<CategoryBadge value={val} />);
      expect(screen.getByText(val)).toBeInTheDocument();
    },
  );

  it("uses sky background for HIL/SW (Sangjun)", () => {
    const { container } = render(<CategoryBadge value="HIL" />);
    expect(container.querySelector(".bg-sky-700")).not.toBeNull();
  });

  it("uses orange variants for ABB hardware lineup", () => {
    const { container } = render(<CategoryBadge value="ABB장비" />);
    expect(container.querySelector(".bg-orange-500")).not.toBeNull();
  });

  it("falls back to slate for unknown category", () => {
    const { container } = render(<CategoryBadge value="UNKNOWN" />);
    expect(container.querySelector(".bg-slate-700")).not.toBeNull();
  });
});
