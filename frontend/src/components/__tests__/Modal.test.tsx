import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "../Modal";

describe("Modal", () => {
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
