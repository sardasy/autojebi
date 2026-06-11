import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ToastProvider } from "../Toast";

const actionUpsertMock = vi.fn();
vi.mock("@/lib/actions", () => ({
  actionUpsert: (...args: unknown[]) => actionUpsertMock(...args),
}));

async function loadForm() {
  const mod = await import("../UpsertNoticeForm");
  return mod.UpsertNoticeForm;
}

describe("UpsertNoticeForm", () => {
  beforeEach(() => {
    actionUpsertMock.mockReset();
  });

  it("shows error message on invalid JSON in raw", async () => {
    const UpsertNoticeForm = await loadForm();
    render(
      <ToastProvider>
        <UpsertNoticeForm />
      </ToastProvider>,
    );
    const textarea = screen.getByText("raw (JSON)").nextElementSibling as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "{broken" } });
    // 검증 메시지 노출
    expect(screen.getByText(/⚠/)).toBeInTheDocument();
  });

  it("renders the upsert button", async () => {
    const UpsertNoticeForm = await loadForm();
    render(
      <ToastProvider>
        <UpsertNoticeForm />
      </ToastProvider>,
    );
    expect(screen.getByRole("button", { name: /Upsert 실행/ })).toBeInTheDocument();
  });
});
