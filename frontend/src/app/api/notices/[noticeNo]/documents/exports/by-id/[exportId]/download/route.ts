import { NextRequest, NextResponse } from "next/server";

import { fetchDownloadBlob } from "@/lib/api";

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ noticeNo: string; exportId: string }> },
) {
  const { noticeNo, exportId } = await ctx.params;
  if (!/^\d+$/.test(exportId)) {
    return NextResponse.json({ error: "invalid export id" }, { status: 400 });
  }
  const path = `/notices/${encodeURIComponent(
    noticeNo,
  )}/documents/exports/by-id/${exportId}/download`;
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
