import Link from "next/link";

import { G2BSearchResults } from "@/components/G2BSearchResults";
import { NoticeFilterBar } from "@/components/NoticeFilterBar";
import { Pagination } from "@/components/Pagination";
import { ScoreBadge } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import {
  getNoticeSummary,
  listNotices,
  searchG2BNotices,
  type Lifecycle,
  type NoticeRecord,
  type NoticeSearchItem,
  type NoticeSummary,
  type SortDirection,
  type SortField,
} from "@/lib/api";
import {
  DEFAULT_DIRECTION,
  DEFAULT_LIFECYCLE,
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT,
} from "@/lib/constants/notices";
import {
  documentSummaryText,
  nextNoticeAction,
  readDocumentAutomation,
} from "@/lib/documentAutomation";

export const dynamic = "force-dynamic";

type Mode = "saved" | "g2b";

function fmtDate(s: string | null): string {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return s.slice(0, 16);
  }
}

function asStr(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v && v !== "" ? v : undefined;
}

function asStrArray(v: string | string[] | undefined): string[] | undefined {
  if (Array.isArray(v)) return v.filter(Boolean);
  return v ? [v] : undefined;
}

function asNum(v: string | string[] | undefined): number | undefined {
  const s = asStr(v);
  if (s === undefined) return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

function toFromIso(d: string | undefined): string | undefined {
  return d ? `${d.slice(0, 10)}T00:00:00` : undefined;
}

function toToIso(d: string | undefined): string | undefined {
  return d ? `${d.slice(0, 10)}T23:59:59` : undefined;
}

export default async function NoticesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;

  const mode: Mode = asStr(params.mode) === "g2b" ? "g2b" : "saved";
  const q = asStr(params.q)?.trim();
  const status = asStrArray(params.status);
  const lifecycle = asStr(params.lifecycle) || DEFAULT_LIFECYCLE;
  const sort = asStr(params.sort) || DEFAULT_SORT;
  const direction = asStr(params.direction) || DEFAULT_DIRECTION;
  const open_from = asStr(params.open_from);
  const open_to = asStr(params.open_to);
  const close_from = asStr(params.close_from);
  const close_to = asStr(params.close_to);
  const page = asNum(params.page) || 1;
  const page_size = asNum(params.page_size) || DEFAULT_PAGE_SIZE;

  const baseQuery = new URLSearchParams();
  baseQuery.set("mode", mode);
  if (q) baseQuery.set("q", q);
  for (const value of status || []) baseQuery.append("status", value);
  if (open_from) baseQuery.set("open_from", open_from);
  if (open_to) baseQuery.set("open_to", open_to);
  if (close_from) baseQuery.set("close_from", close_from);
  if (close_to) baseQuery.set("close_to", close_to);
  baseQuery.set("page_size", String(page_size));
  if (mode === "saved") {
    baseQuery.set("lifecycle", lifecycle);
    baseQuery.set("sort", sort);
    baseQuery.set("direction", direction);
  }

  return mode === "g2b" ? (
    <G2BMode
      q={q}
      open_from={open_from}
      open_to={open_to}
      close_from={close_from}
      close_to={close_to}
      page={page}
      page_size={page_size}
      baseQuery={baseQuery}
    />
  ) : (
    <SavedMode
      q={q}
      status={status}
      lifecycle={lifecycle}
      sort={sort}
      direction={direction}
      page={page}
      page_size={page_size}
      baseQuery={baseQuery}
    />
  );
}

async function SavedMode({
  q,
  status,
  lifecycle,
  sort,
  direction,
  page,
  page_size,
  baseQuery,
}: {
  q?: string;
  status?: string[];
  lifecycle: string;
  sort: string;
  direction: string;
  page: number;
  page_size: number;
  baseQuery: URLSearchParams;
}) {
  let items: NoticeRecord[] = [];
  let total = 0;
  let total_pages = 0;
  let summary: NoticeSummary | null = null;
  let error: string | null = null;

  try {
    const [listResp, summaryResp] = await Promise.all([
      listNotices({
        q,
        status,
        lifecycle: lifecycle as Lifecycle,
        sort: sort as SortField,
        direction: direction as SortDirection,
        page,
        page_size,
      }),
      getNoticeSummary(),
    ]);
    items = listResp.items;
    total = listResp.total || 0;
    total_pages = listResp.total_pages || 0;
    summary = summaryResp;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-6">
      <Header title="저장 공고 업무 큐" />
      <NoticeFilterBar
        mode="saved"
        q={q}
        status={status}
        lifecycle={lifecycle}
        sort={sort}
        direction={direction}
        page_size={String(page_size)}
      />

      {summary ? <SummaryCards summary={summary} /> : null}

      {error ? (
        <ErrorBox title="저장 공고를 불러올 수 없습니다" error={error} />
      ) : items.length === 0 ? (
        <EmptyBox>
          저장된 진행 공고가 없습니다.{" "}
          <Link href="/notices?mode=g2b" className="text-brand-400 hover:underline">
            G2B에서 검색하기
          </Link>
        </EmptyBox>
      ) : (
        <>
          <Pagination
            page={page}
            totalPages={total_pages}
            total={total}
            pageSize={page_size}
            baseQuery={baseQuery}
          />
          <SavedNoticesTable items={items} />
          <div className="flex justify-end">
            <Pagination
              page={page}
              totalPages={total_pages}
              total={total}
              pageSize={page_size}
              baseQuery={baseQuery}
            />
          </div>
        </>
      )}
    </div>
  );
}

async function G2BMode({
  q,
  open_from,
  open_to,
  close_from,
  close_to,
  page,
  page_size,
  baseQuery,
}: {
  q?: string;
  open_from?: string;
  open_to?: string;
  close_from?: string;
  close_to?: string;
  page: number;
  page_size: number;
  baseQuery: URLSearchParams;
}) {
  const startDate = open_from || close_from;
  const endDate = open_to || close_to;
  let items: NoticeSearchItem[] = [];
  let total = 0;
  let total_pages = 0;
  let error: string | null = null;

  if (q) {
    try {
      const resp = await searchG2BNotices({
        keyword: q,
        start_date: toFromIso(startDate),
        end_date: toToIso(endDate),
        page,
        page_size,
      });
      items = resp.items;
      total = resp.total;
      total_pages = resp.total_pages;
    } catch (e) {
      error = (e as Error).message;
    }
  }

  return (
    <div className="space-y-6">
      <Header title="G2B 실시간 공고 검색" />
      <NoticeFilterBar
        mode="g2b"
        q={q}
        open_from={open_from}
        open_to={open_to}
        close_from={close_from}
        close_to={close_to}
        page_size={String(page_size)}
      />

      {!q ? (
        <EmptyBox>
          검색어를 입력하면 나라장터 OpenAPI를 새로 조회합니다. 저장된 공고는{" "}
          <Link href="/notices?mode=saved" className="text-brand-400 hover:underline">
            저장 공고
          </Link>
          에서 확인합니다.
        </EmptyBox>
      ) : error ? (
        <ErrorBox title="G2B 검색 실패" error={error} />
      ) : items.length === 0 ? (
        <EmptyBox>
          조건에 맞는 G2B 공고가 없습니다.{" "}
          <Link href="/notices?mode=g2b" className="text-brand-400 hover:underline">
            초기화
          </Link>
        </EmptyBox>
      ) : (
        <>
          <Pagination
            page={page}
            totalPages={total_pages}
            total={total}
            pageSize={page_size}
            baseQuery={baseQuery}
          />
          <G2BSearchResults items={items} />
          <div className="flex justify-end">
            <Pagination
              page={page}
              totalPages={total_pages}
              total={total}
              pageSize={page_size}
              baseQuery={baseQuery}
            />
          </div>
          <p className="text-xs text-slate-500">
            최대 365일까지 검색할 수 있습니다. 저장 시 source=G2B로 등록되며,
            저장 후 상세 화면에서 분석과 서류 준비를 진행합니다.
          </p>
        </>
      )}
    </div>
  );
}

function Header({ title }: { title: string }) {
  return (
    <section className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="mt-1 text-sm text-slate-400">
          저장된 공고를 처리하고, 필요한 경우 G2B에서 신규 공고를 찾아 등록합니다.
        </p>
      </div>
    </section>
  );
}

function SummaryCards({ summary }: { summary: NoticeSummary }) {
  const cards = [
    ["진행 공고", summary.active_total],
    ["오늘 마감", summary.closing_today],
    ["7일 내 마감", summary.closing_7d],
    ["분석 필요", summary.needs_analysis],
    ["Grade 필요", summary.needs_grade],
    ["제출 준비", summary.ready_for_submission],
    ["서류 막힘", summary.blocked_documents],
  ];
  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {cards.map(([label, value]) => (
        <div key={label} className="rounded border border-slate-800 bg-slate-900/40 p-3">
          <div className="text-xs text-slate-500">{label}</div>
          <div className="mt-1 text-xl font-semibold text-slate-100">{value}</div>
        </div>
      ))}
    </section>
  );
}

function SavedNoticesTable({ items }: { items: NoticeRecord[] }) {
  return (
    <div className="overflow-x-auto rounded border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900/80 text-slate-300">
          <tr>
            <Th>공고번호</Th>
            <Th>제목</Th>
            <Th>기관</Th>
            <Th>마감</Th>
            <Th>상태</Th>
            <Th>fit</Th>
            <Th>종합점수</Th>
            <Th>추천 SKU</Th>
            <Th>서류 준비</Th>
            <Th>다음 작업</Th>
          </tr>
        </thead>
        <tbody>
          {items.map((notice) => {
            const docs = readDocumentAutomation(notice);
            return (
              <tr
                key={notice.notice_no}
                className="border-t border-slate-800 hover:bg-slate-900/40"
              >
                <Td className="font-mono text-xs text-slate-300">
                  {notice.notice_no}
                </Td>
                <Td>
                  <Link
                    href={`/notices/${encodeURIComponent(notice.notice_no)}`}
                    className="text-slate-100 hover:text-brand-500"
                  >
                    {notice.title || notice.notice_no}
                  </Link>
                </Td>
                <Td className="text-slate-300">{notice.org_name || "-"}</Td>
                <Td className="text-xs text-slate-300">{fmtDate(notice.close_date)}</Td>
                <Td>
                  <StatusBadge value={notice.status} />
                </Td>
                <Td>
                  <ScoreBadge value={notice.fit_score} mode="0to100" />
                </Td>
                <Td>
                  <ScoreBadge value={notice.score_total} />
                </Td>
                <Td className="text-slate-300">
                  {notice.top_sku_name || notice.top_sku || "-"}
                </Td>
                <Td className="min-w-[220px] text-xs text-slate-300">
                  {docs ? documentSummaryText(docs) : "서류 분석 전"}
                </Td>
                <Td>
                  <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
                    {nextNoticeAction(notice)}
                  </span>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EmptyBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
      {children}
    </div>
  );
}

function ErrorBox({ title, error }: { title: string; error: string }) {
  return (
    <div className="rounded border border-red-700 bg-red-950/40 p-4 text-sm">
      <p className="font-semibold text-red-300">{title}</p>
      <p className="mt-1 text-slate-300">{error}</p>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-3 py-2 text-left font-medium">{children}</th>;
}

function Td({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-3 py-2 ${className || ""}`}>{children}</td>;
}
