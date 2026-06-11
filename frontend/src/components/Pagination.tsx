import Link from "next/link";

type Props = {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  /** 현재 URL의 모든 다른 쿼리(검색 조건 등). 페이지 이동 시 유지. */
  baseQuery: URLSearchParams;
};

/**
 * 페이지네이션 — `?page=N` 으로 이동. 양 끝 / 가까운 페이지 5개 + 점프 표시.
 */
export function Pagination({ page, totalPages, total, pageSize, baseQuery }: Props) {
  if (totalPages <= 1) {
    return (
      <div className="text-xs text-slate-400">
        총 <span className="text-slate-200">{total.toLocaleString("ko-KR")}</span>건
      </div>
    );
  }

  const makeHref = (p: number) => {
    const q = new URLSearchParams(baseQuery);
    q.set("page", String(p));
    q.set("page_size", String(pageSize));
    return `/notices?${q.toString()}`;
  };

  const window = 2;
  const start = Math.max(1, page - window);
  const end = Math.min(totalPages, page + window);
  const pages: number[] = [];
  for (let i = start; i <= end; i++) pages.push(i);

  return (
    <nav className="flex items-center gap-1 text-xs">
      <span className="text-slate-400 mr-2">
        총 <span className="text-slate-200">{total.toLocaleString("ko-KR")}</span>건 · 페이지{" "}
        <span className="text-slate-200">
          {page}/{totalPages}
        </span>
      </span>
      <PageLink
        href={page > 1 ? makeHref(1) : null}
        label="«"
        title="첫 페이지"
      />
      <PageLink
        href={page > 1 ? makeHref(page - 1) : null}
        label="‹"
        title="이전"
      />
      {start > 1 && <span className="px-1 text-slate-500">…</span>}
      {pages.map((p) => (
        <PageLink
          key={p}
          href={p === page ? null : makeHref(p)}
          label={String(p)}
          active={p === page}
        />
      ))}
      {end < totalPages && <span className="px-1 text-slate-500">…</span>}
      <PageLink
        href={page < totalPages ? makeHref(page + 1) : null}
        label="›"
        title="다음"
      />
      <PageLink
        href={page < totalPages ? makeHref(totalPages) : null}
        label="»"
        title="마지막"
      />
    </nav>
  );
}

function PageLink({
  href,
  label,
  active,
  title,
}: {
  href: string | null;
  label: string;
  active?: boolean;
  title?: string;
}) {
  const cls = active
    ? "bg-brand-500 text-white"
    : href
      ? "bg-slate-900 text-slate-200 hover:bg-slate-800"
      : "bg-slate-950 text-slate-600 cursor-not-allowed";
  if (!href) {
    return (
      <span className={`px-2 py-1 rounded border border-slate-800 ${cls}`} aria-disabled>
        {label}
      </span>
    );
  }
  return (
    <Link
      href={href}
      title={title}
      className={`px-2 py-1 rounded border border-slate-800 ${cls}`}
    >
      {label}
    </Link>
  );
}
