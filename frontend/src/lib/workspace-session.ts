import {NextRequest} from "next/server";

export const workspaceSessionCookie = "autojebi_workspace_session";
export const workspaceSessionSeconds = 8 * 60 * 60;

export interface WorkspaceIdentity {
  enabled: boolean;
  actor: {id: string; name: string; role: "viewer" | "writer" | "reviewer" | "approver"} | null;
}

export function sameWorkspaceOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  const allowed = (process.env.FRONTEND_ORIGIN || "http://127.0.0.1:3002").split(",").map(value => value.trim());
  return !!origin && allowed.includes(origin);
}

export async function readWorkspaceIdentity(token?: string): Promise<Response> {
  const headers = new Headers();
  if (process.env.INTERNAL_API_KEY) headers.set("X-API-Key", process.env.INTERNAL_API_KEY);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${process.env.INTERNAL_API_BASE || "http://127.0.0.1:8002"}/v2/identity`, {
    headers, cache: "no-store", signal: AbortSignal.timeout(10000),
  });
}
