import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const revalidatePathMock = vi.fn();
vi.mock("next/cache", () => ({
  revalidatePath: (...args: unknown[]) => revalidatePathMock(...args),
}));

const originalFetch = global.fetch;

describe("Server Actions", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
    revalidatePathMock.mockReset();
  });
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("actionGrade revalidates detail + list paths", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ score_total: 0.8 }),
    });
    const { actionGrade } = await import("../actions");
    await actionGrade("T1-00", true);
    expect(revalidatePathMock).toHaveBeenCalledWith("/notices/T1-00");
    expect(revalidatePathMock).toHaveBeenCalledWith("/notices");
  });

  it("actionUpsert revalidates /notices", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ notice_no: "N" }),
    });
    const { actionUpsert } = await import("../actions");
    await actionUpsert({ notice_no: "N" });
    expect(revalidatePathMock).toHaveBeenCalledWith("/notices");
  });

  it("actionIngestSkus does NOT revalidate (one-off admin)", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ingested: 23, collection: "abb_skus" }),
    });
    const { actionIngestSkus } = await import("../actions");
    await actionIngestSkus();
    expect(revalidatePathMock).not.toHaveBeenCalled();
  });
});
