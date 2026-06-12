import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const originalFetch = global.fetch;

describe("api client", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("listNotices hits /notices with query string", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }),
    });
    const { listNotices } = await import("../api");
    await listNotices({ status: ["analyzed"], min_fit_score: 70 });

    const call = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/notices");
    expect(call[0]).toContain("status=analyzed");
    expect(call[0]).toContain("min_fit_score=70");
    expect(call[1].cache).toBe("no-store");
  });

  it("listNotices serializes array values as repeated params", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }),
    });
    const { listNotices } = await import("../api");
    await listNotices({
      status: ["analyzed", "form_filled"],
      category: ["IGBT", "SCR"],
    });

    const url = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("status=analyzed");
    expect(url).toContain("status=form_filled");
    expect(url).toContain("category=IGBT");
    expect(url).toContain("category=SCR");
    // 같은 키가 두 번 등장 — 콤마 합치기 아님
    expect(url.match(/status=/g)?.length).toBe(2);
  });

  it("listNotices serializes boolean filters", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }),
    });
    const { listNotices } = await import("../api");
    await listNotices({
      has_grade: true,
      ready_for_submission: false,
      lifecycle: "active",
    });
    const url = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("has_grade=true");
    expect(url).toContain("ready_for_submission=false");
    expect(url).toContain("lifecycle=active");
  });

  it("qs round-trips ListFilters as URLSearchParams", async () => {
    const { qs } = await import("../api");
    const s = qs({
      q: "한전",
      status: ["analyzed", "form_filled"],
      page: 2,
      page_size: 20,
      has_grade: true,
    });
    const usp = new URLSearchParams(s.replace(/^\?/, ""));
    expect(usp.get("q")).toBe("한전");
    expect(usp.getAll("status")).toEqual(["analyzed", "form_filled"]);
    expect(usp.get("page")).toBe("2");
    expect(usp.get("page_size")).toBe("20");
    expect(usp.get("has_grade")).toBe("true");
  });

  it("gradeNotice POSTs with alert body", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ score_total: 0.7 }),
    });
    const { gradeNotice } = await import("../api");
    await gradeNotice("T1-00", true);

    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/notices/T1-00/grade");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ alert: true });
  });

  it("notifyNotice translates dryRun → dry_run", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    const { notifyNotice } = await import("../api");
    await notifyNotice("T1-00", false);

    const init = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(init.body as string)).toEqual({ dry_run: false });
  });

  it("autofillForm sends full payload", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    const { autofillForm } = await import("../api");
    await autofillForm("T1-00", {
      template_path: "templates/x.hwp",
      output_path: "output/y.hwp",
      values: { a: "b" },
      visible: false,
    });

    const body = JSON.parse(
      (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body.template_path).toBe("templates/x.hwp");
    expect(body.values).toEqual({ a: "b" });
  });

  it("throws Error with status on non-200", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: async () => ({ detail: "no key" }),
    });
    const { analyzeNotice } = await import("../api");
    await expect(analyzeNotice("X")).rejects.toThrow(/403/);
  });

});
