import { NextRequest } from "next/server";
import {sameWorkspaceOrigin, workspaceSessionCookie} from "@/lib/workspace-session";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  const { path } = await context.params;
  if (path.some(p => !p || p === "." || p === ".." || /[\\/?#]/.test(p))) {
    return Response.json({ detail: { message: "잘못된 요청 경로입니다." } }, { status: 400 });
  }
  if (request.method !== "GET") {
    if (!sameWorkspaceOrigin(request)) {
      return Response.json({ detail: { message: "다른 출처의 변경 요청은 허용하지 않습니다." } }, { status: 403 });
    }
  }
  const base = process.env.INTERNAL_API_BASE || "http://127.0.0.1:8002";
  const headers = new Headers();
  if (process.env.INTERNAL_API_KEY) headers.set("X-API-Key", process.env.INTERNAL_API_KEY);
  const session = request.cookies.get(workspaceSessionCookie)?.value;
  if (session) headers.set("Authorization", `Bearer ${session}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const ifMatch = request.headers.get("if-match");
  if (ifMatch) headers.set("If-Match", ifMatch);
  try {
    const response = await fetch(`${base}/v2/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, {
      method: request.method, headers, body: request.method === "GET" ? undefined : await request.arrayBuffer(), cache: "no-store",
      signal: AbortSignal.timeout(120000),
    });
    const out = new Headers();
    for (const name of ["content-type", "content-disposition", "x-page-count", "etag", "x-form-sha256", "x-form-review", "cache-control"]) {
      const value = response.headers.get(name);
      if (value) out.set(name, value);
    }
    return new Response(response.body, { status: response.status, headers: out });
  } catch {
    return Response.json({ detail: { code: "api_unavailable", message: "API에 연결할 수 없습니다.", next_action: "관리자에서 연결을 확인하세요." } }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
