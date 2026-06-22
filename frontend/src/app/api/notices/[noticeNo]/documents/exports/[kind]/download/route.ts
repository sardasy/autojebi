import { NextRequest, NextResponse } from "next/server";

import { fetchDownloadBlob } from "@/lib/api";

/**
 * Excel/HWP export 다운로드 프록시 (M11 v2 + M14 proposal).
 *
 * 브라우저에서 `<a href="/api/notices/.../documents/exports/excel/download">` 클릭 시
 * X-API-Key 헤더 직접 전달이 어려우므로, Next.js API route가 서버사이드에서
 * INTERNAL_API_KEY를 주입해 백엔드를 호출하고 응답 blob을 그대로 스트리밍.
 */
export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ noticeNo: string; kind: string }> },
) {
  const { noticeNo, kind } = await ctx.params;
  if (kind !== "excel" && kind !== "hwp" && kind !== "proposal_hwp") {
    return NextResponse.json({ error: "invalid kind" }, { status: 400 });
  }
  const path = `/notices/${encodeURIComponent(noticeNo)}/documents/exports/${kind}/download`;
  const upstream = await fetchDownloadBlob(path);
  if (!upstream.ok) {
    return NextResponse.json(
      { error: `upstream ${upstream.status}` },
      { status: upstream.status },
    );
  }
  const blob = await upstream.arrayBuffer();
  const headers = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  const cd = upstream.headers.get("content-disposition");
  if (cd) headers.set("content-disposition", cd);
  return new NextResponse(blob, { status: 200, headers });
}
