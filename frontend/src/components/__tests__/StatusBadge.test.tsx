import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "../StatusBadge";

describe("StatusBadge", () => {
  const cases: [string, string][] = [
    ["collected", "수집"],
    ["analyzed", "분석"],
    ["attachments_fetched", "첨부"],
    ["documents_analyzed", "서류"],
    ["spec_extracted", "규격"],
    ["hwp_composed", "HWP"],
    ["form_filled", "작성"],
    ["notified", "알림"],
    ["digest_queued", "다이제스트"],
    ["archived_low", "보류"],
  ];

  it.each(cases)("maps %s to Korean label %s", (value, label) => {
    render(<StatusBadge value={value} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("emerald color for notified (강조)", () => {
    const { container } = render(<StatusBadge value="notified" />);
    expect(container.querySelector(".bg-emerald-600")).not.toBeNull();
  });

  it("falls back gracefully for unknown status", () => {
    const { container } = render(<StatusBadge value="WIP" />);
    expect(container.querySelector(".bg-slate-700")).not.toBeNull();
  });
});
