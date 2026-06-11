import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "../Toast";

function Trigger({ kind, msg }: { kind: "success" | "error" | "info"; msg: string }) {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast.push(kind, msg)}>
      push
    </button>
  );
}

describe("Toast", () => {
  it("renders pushed toast", () => {
    render(
      <ToastProvider>
        <Trigger kind="success" msg="OK" />
      </ToastProvider>,
    );
    act(() => {
      screen.getByText("push").click();
    });
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("auto-dismisses after 5 seconds", () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <Trigger kind="info" msg="HELLO" />
        </ToastProvider>,
      );
      act(() => {
        screen.getByText("push").click();
      });
      expect(screen.getByText("HELLO")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(5001);
      });
      expect(screen.queryByText("HELLO")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("throws when useToast called outside provider", () => {
    function BadComp() {
      useToast();
      return null;
    }
    // suppress error log
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<BadComp />)).toThrow();
    spy.mockRestore();
  });
});
