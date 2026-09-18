import {NextRequest, NextResponse} from "next/server";
import {readWorkspaceIdentity, sameWorkspaceOrigin, WorkspaceIdentity, workspaceSessionCookie, workspaceSessionSeconds} from "@/lib/workspace-session";

export const dynamic = "force-dynamic";

function error(status: number, message: string) {
  return NextResponse.json({detail: {message}}, {status, headers: {"Cache-Control": "no-store"}});
}

function validIdentity(value: unknown): value is WorkspaceIdentity {
  if (!value || typeof value !== "object" || !("enabled" in value) || typeof value.enabled !== "boolean" || !("actor" in value)) return false;
  if (!value.enabled) return value.actor === null;
  const actor = value.actor;
  return !!actor && typeof actor === "object" && "id" in actor && typeof actor.id === "string"
    && "name" in actor && typeof actor.name === "string" && "role" in actor
    && ["viewer", "writer", "reviewer", "approver"].includes(String(actor.role));
}

async function identity(token?: string): Promise<WorkspaceIdentity | NextResponse> {
  try {
    const response = await readWorkspaceIdentity(token);
    if (!response.ok) return error(response.status, response.status === 401 ? "개인 계정으로 로그인하세요." : "개인 인증 설정 또는 연결을 확인하세요.");
    const value: unknown = await response.json();
    if (!validIdentity(value)) return error(502, "개인 인증 응답을 확인할 수 없습니다.");
    // Copy only identity fields: upstream responses must never leak credential material.
    return {enabled: value.enabled, actor: value.actor ? {id: value.actor.id, name: value.actor.name, role: value.actor.role} : null};
  } catch {
    return error(502, "개인 인증 서버에 연결할 수 없습니다.");
  }
}

export async function GET(request: NextRequest) {
  const result = await identity(request.cookies.get(workspaceSessionCookie)?.value);
  return result instanceof NextResponse ? result : NextResponse.json(result, {headers: {"Cache-Control": "no-store"}});
}

export async function POST(request: NextRequest) {
  if (!sameWorkspaceOrigin(request)) return error(403, "다른 출처의 로그인 요청은 허용하지 않습니다.");
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) return error(415, "로그인 요청 형식을 확인하세요.");
  let token: string;
  try {
    const text = await request.text();
    if (text.length > 2048) return error(400, "개인 인증 정보를 확인하세요.");
    const body: unknown = JSON.parse(text);
    if (!body || typeof body !== "object" || !("token" in body) || typeof body.token !== "string"
      || !/^[A-Za-z0-9._~+/=-]{32,512}$/.test(body.token)) return error(400, "개인 인증 정보를 확인하세요.");
    token = body.token;
  } catch {
    return error(400, "로그인 요청 형식을 확인하세요.");
  }
  const result = await identity(token);
  if (result instanceof NextResponse) return result;
  if (!result.enabled || !result.actor) return error(409, "이 환경은 개인 인증을 사용하지 않습니다.");
  const response = NextResponse.json(result, {headers: {"Cache-Control": "no-store"}});
  response.cookies.set(workspaceSessionCookie, token, {
    httpOnly: true, sameSite: "strict", secure: process.env.NODE_ENV === "production" || request.nextUrl.protocol === "https:",
    path: "/", maxAge: workspaceSessionSeconds,
  });
  return response;
}

export async function DELETE(request: NextRequest) {
  if (!sameWorkspaceOrigin(request)) return error(403, "다른 출처의 로그아웃 요청은 허용하지 않습니다.");
  const response = NextResponse.json({ok: true}, {headers: {"Cache-Control": "no-store"}});
  response.cookies.set(workspaceSessionCookie, "", {httpOnly: true, sameSite: "strict", path: "/", maxAge: 0,
    secure: process.env.NODE_ENV === "production" || request.nextUrl.protocol === "https:"});
  return response;
}
