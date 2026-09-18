// @vitest-environment node
import {beforeEach, afterEach, describe, expect, it, vi} from "vitest";
import {NextRequest} from "next/server";
import {DELETE, GET, POST} from "@/app/api/workspace-session/route";
import {GET as proxyGet, POST as proxyPost} from "@/app/api/v2/[...path]/route";
import {workspaceSessionCookie} from "../workspace-session";

const token = "fixture-personal-token-" + "x".repeat(40);
const actor = {id: "writer", name: "Test Writer", role: "writer"};
const origin = "http://127.0.0.1:3002";
const request = (method = "GET", extra: Record<string, string> = {}, body?: unknown, url = "/api/workspace-session") => new NextRequest(`${origin}${url}`, {
  method, headers: {origin, "content-type": "application/json", ...extra}, body: body === undefined ? undefined : JSON.stringify(body),
});

describe("workspace personal session and trusted proxy", () => {
  beforeEach(() => {
    vi.stubEnv("FRONTEND_ORIGIN", origin);
    vi.stubEnv("INTERNAL_API_KEY", "fixture-shared-key");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({enabled: true, actor, token_sha256: "must-not-return"})));
  });
  afterEach(() => {vi.unstubAllEnvs(); vi.unstubAllGlobals();});
  it("validates a personal token before setting a bounded HttpOnly SameSite session", async () => {
    const response = await POST(request("POST", {}, {token, actor: {role: "approver"}}));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({enabled: true, actor});
    const cookie = response.headers.get("set-cookie")!;
    expect(cookie).toContain("HttpOnly"); expect(cookie).toContain("SameSite=strict"); expect(cookie).toContain("Max-Age=28800");
    const upstream = vi.mocked(fetch).mock.calls[0][1]!;
    expect(new Headers(upstream.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(new Headers(upstream.headers).get("X-API-Key")).toBe("fixture-shared-key");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });
  it.each(["https://evil.example", ""])("blocks login and logout from untrusted origin %s", async badOrigin => {
    expect((await POST(request("POST", {origin: badOrigin}, {token}))).status).toBe(403);
    expect((await DELETE(request("DELETE", {origin: badOrigin}))).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not set a session on rejected or disabled authentication and clears it on logout", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(Response.json({detail: "invalid secret"}, {status: 401}));
    const denied = await POST(request("POST", {}, {token}));
    expect(denied.status).toBe(401); expect(denied.headers.get("set-cookie")).toBeNull();
    expect(await denied.text()).not.toContain("invalid secret");
    vi.mocked(fetch).mockResolvedValueOnce(Response.json({enabled: false, actor: null}));
    expect((await POST(request("POST", {}, {token}))).status).toBe(409);
    const logout = await DELETE(request("DELETE"));
    expect(logout.headers.get("set-cookie")).toContain("Max-Age=0");
  });
  it("reads identity using only the HttpOnly credential cookie", async () => {
    const response = await GET(request("GET", {cookie: `${workspaceSessionCookie}=${token}`, Authorization: "Bearer forged"}));
    expect(await response.json()).toEqual({enabled: true, actor});
    expect(new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers).get("Authorization")).toBe(`Bearer ${token}`);
  });
  it("forwards personal credentials from cookies and discards forged identity and role headers", async () => {
    const context = {params: Promise.resolve({path: ["notices", "N", "workspace"]})};
    await proxyGet(request("GET", {cookie: `${workspaceSessionCookie}=${token}`, Authorization: "Bearer forged", "X-Actor-Id": "other", "X-Workspace-Role": "approver", "X-API-Key": "forged"}, undefined, "/api/v2/notices/N/workspace"), context);
    const headers = new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers);
    expect(headers.get("Authorization")).toBe(`Bearer ${token}`);
    expect(headers.get("X-API-Key")).toBe("fixture-shared-key");
    expect(headers.has("X-Actor-Id")).toBe(false); expect(headers.has("X-Workspace-Role")).toBe(false);
    vi.mocked(fetch).mockClear();
    await proxyGet(request("GET", {Authorization: "Bearer forged"}), context);
    expect(new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers).has("Authorization")).toBe(false);
  });
  it("blocks cross-origin mutations before forwarding credentials", async () => {
    const response = await proxyPost(request("POST", {origin: "https://evil.example", cookie: `${workspaceSessionCookie}=${token}`}, {}), {params: Promise.resolve({path: ["notices", "N", "reviews"]})});
    expect(response.status).toBe(403); expect(fetch).not.toHaveBeenCalled();
  });
  it("keeps a fixed local fallback when the requested host and Origin are both forged", async () => {
    vi.stubEnv("FRONTEND_ORIGIN", "");
    const forged = () => new NextRequest("https://evil.example/api/workspace-session", {
      method: "POST", headers: {origin: "https://evil.example", host: "evil.example", "content-type": "application/json"}, body: JSON.stringify({token}),
    });
    expect((await POST(forged())).status).toBe(403);
    const denied = await proxyPost(forged(), {params: Promise.resolve({path: ["notices", "N", "reviews"]})});
    expect(denied.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
    expect((await POST(request("POST", {}, {token}))).status).toBe(200);
  });
});
