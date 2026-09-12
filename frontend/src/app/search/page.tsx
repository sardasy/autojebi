import Link from "next/link";

import { Step1Search } from "@/components/Step1Search";
import { listNotices, type NoticeRecord } from "@/lib/api";

export const dynamic = "force-dynamic";

function fmtDate(s: string | null): string {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleDateString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return s.slice(0, 10);
  }
}

export default async function SearchPage() {
  let recent: NoticeRecord[];
  try {
    const res = await listNotices({ sort: "updated_at", direction: "desc", page_size: 8 });
    recent = res.items;
  } catch {
    recent = [];
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold text-slate-900">공고 검색</h1>
      <div className="mb-5"/>

      <Step1Search />

      {recent.length > 0 ? (
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">이어서 작업</h2>
          <ul className="space-y-2">
            {recent.map((n) => (
              <li key={n.notice_no}>
                <Link
                  href={`/notices/${encodeURIComponent(n.notice_no)}`}
                  className="flex items-center gap-3 rounded border border-slate-200 bg-slate-50/40 p-3 hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-slate-900">
                      {n.title || n.notice_no}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-slate-600">
                      <span className="font-mono">{n.notice_no}</span>
                      <span>{n.org_name || "-"}</span>
                      <span>마감 {fmtDate(n.close_date)}</span>
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-brand-500">계속 →</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
