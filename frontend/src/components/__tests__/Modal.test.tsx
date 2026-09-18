import { render, screen, fireEvent } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "../Modal";

describe("Modal", () => {
  it("returns focus and restores body scrolling when closed", () => {
    function Harness() {
      const [open,setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>열기</button><Modal open={open} onClose={() => setOpen(false)} title="검토"><button>확인</button></Modal></>;
    }
    render(<Harness/>);
    const trigger = screen.getByRole("button", { name: "열기" });
    trigger.focus(); fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).not.toBe("hidden");
  });
  it("renders title and children when open", () => {
    render(
      <Modal open={true} onClose={() => {}} title="T">
        <p>body</p>
      </Modal>,
    );
    expect(screen.getByText("T")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <Modal open={false} onClose={() => {}} title="T">
        <p>body</p>
      </Modal>,
    );
    expect(container.firstChild).toBeNull();
  });

  it("invokes onClose on ESC", () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("invokes onClose on close button click", () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    );
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalled();
  });
});
