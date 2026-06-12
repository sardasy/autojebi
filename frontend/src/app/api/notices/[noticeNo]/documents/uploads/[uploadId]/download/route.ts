import { NextRequest, NextResponse } from "next/server";

import { fetchDownloadBlob } from "@/lib/api";

/**
 * 사용자가 업로드한 파일 다운로드 프록시 (M11 v2).
 */
export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ noticeNo: string; uploadId: string }> },
) {
  const { noticeNo, uploadId } = await ctx.params;
  const path = `/notices/${encodeURIComponent(noticeNo)}/documents/uploads/${encodeURIComponent(uploadId)}/download`;
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
