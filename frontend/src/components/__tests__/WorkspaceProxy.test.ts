import {createHash} from "node:crypto";
import {NextRequest} from "next/server";
import {afterEach, describe, expect, it, vi} from "vitest";
import {GET} from "@/app/api/v2/[...path]/route";

afterEach(() => {vi.unstubAllGlobals(); vi.unstubAllEnvs();});

describe("original form download proxy", () => {
  it("preserves the binary attachment, filename, verification metadata and no-store response", async () => {
    const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0xff, 0x80, 0x0d, 0x0a]);
    const hash = createHash("sha256").update(bytes).digest("hex");
    const disposition = `attachment; filename*=UTF-8''${encodeURIComponent("작성된 첨부양식.hwpx")}`;
    const fetchMock = vi.fn().mockResolvedValue(new Response(bytes, {status: 200, headers: {
      "Content-Type": "application/hwp+zip", "Content-Disposition": disposition,
      "X-Form-SHA256": hash, "X-Form-Review": "pending", "Cache-Control": "no-store",
      "X-Internal-Detail": "must-not-be-forwarded",
    }}));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("INTERNAL_API_BASE", "http://127.0.0.1:8002");
    const path = ["notices", "NOTICE-000", "form-fillings", "document-id", "download"];
    const response = await GET(new NextRequest(`http://127.0.0.1:3002/api/v2/${path.join("/")}`), {params: Promise.resolve({path})});
    expect(fetchMock).toHaveBeenCalledWith(`http://127.0.0.1:8002/v2/${path.join("/")}`, expect.objectContaining({method: "GET", cache: "no-store"}));
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/hwp+zip");
    expect(response.headers.get("content-disposition")).toBe(disposition);
    expect(response.headers.get("x-form-review")).toBe("pending");
    expect(response.headers.get("cache-control")).toBe("no-store");
    const downloaded = new Uint8Array(await response.arrayBuffer());
    expect(downloaded).toEqual(bytes);
    expect(response.headers.get("x-form-sha256")).toBe(createHash("sha256").update(downloaded).digest("hex"));
    expect(response.headers.get("x-internal-detail")).toBeNull();
  });
});
