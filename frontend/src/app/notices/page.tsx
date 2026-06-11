import Link from "next/link";

import { CategoryBadge } from "@/components/CategoryBadge";
import { NoticeFilterBar } from "@/components/NoticeFilterBar";
import { Pagination } from "@/components/Pagination";
import { ScoreBadge } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import {
  listNotices,
  type Lifecycle,
  type NoticeRecord,
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
  readDocumentAutomation,
} from "@/lib/documentAutomation";

export const dynamic = "force-dynamic";

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

function fmtPrice(p: number | string | null): string {
  if (p === null || p === undefined || p === "") return "-";
  const n = typeof p === "string" ? parseFloat(p) : p;
  if (isNaN(n)) return "-";
  return new Intl.NumberFormat("ko-KR").format(n) + "원";
}

function asStr(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v && v !== "" ? v : undefined;
}
function asArr(v: string | string[] | undefined): string[] {
  if (!v) return [];
  if (Array.isArray(v)) return v.filter((x) => x && x !== "");
  return v ? [v] : [];
}
function asNum(v: string | string[] | undefined): number | undefined {
  const s = asStr(v);
  if (s === undefined) return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}
function asBool(v: string | string[] | undefined): boolean | undefined {
  const s = asStr(v);
  if (s === undefined) return undefined;
  if (s === "true") return true;
  if (s === "false") return false;
  return undefined;
}

export default async function NoticesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;

  const hasAnyQuery = Object.values(params).some(
    (v) => v !== undefined && v !== "" && (!Array.isArray(v) || v.length > 0),
  );

  // 기본 텍스트
  const q = asStr(params.q);
  const org_name = asStr(params.org_name);
  const assignee = asStr(params.assignee);

  // 다중
  const status = asArr(params.status);
  const category = asArr(params.category);
  const bid_type = asArr(params.bid_type);
  const source = asArr(params.source);

  // 날짜 (yyyy-mm-dd)
  const open_from = asStr(params.open_from);
  const open_to = asStr(params.open_to);
  const close_from = asStr(params.close_from);
  const close_to = asStr(params.close_to);

  // 숫자 범위
  const min_base_price = asNum(params.min_base_price);
  const max_base_price = asNum(params.max_base_price);
  const min_fit_score = asNum(params.min_fit_score);
  const max_fit_score = asNum(params.max_fit_score);
  const min_score_total = asNum(params.min_score_total);
  const max_score_total = asNum(params.max_score_total);

  // bool 3-state
  const has_grade = asBool(params.has_grade);
  const has_documents = asBool(params.has_documents);
  const has_uploads = asBool(params.has_uploads);
  const ready_for_submission = asBool(params.ready_for_submission);

  // 정렬·페이지·라이프사이클
  const sort = (asStr(params.sort) || DEFAULT_SORT) as SortField;
  const direction = (asStr(params.direction) || DEFAULT_DIRECTION) as SortDirection;
  const lifecycle = (asStr(params.lifecycle) ||
    (hasAnyQuery ? "all" : DEFAULT_LIFECYCLE)) as Lifecycle;
  const page = asNum(params.page) || 1;
  const page_size = asNum(params.page_size) || DEFAULT_PAGE_SIZE;

  // yyyy-mm-dd → ISO datetime (날짜 범위는 하루 단위로 from 00:00, to 23:59 적용)
  const toFromIso = (d: string | undefined) =>
    d ? `${d.slice(0, 10)}T00:00:00` : undefined;
  const toToIso = (d: string | undefined) =>
    d ? `${d.slice(0, 10)}T23:59:59` : undefined;

  let items: NoticeRecord[] = [];
  let total = 0;
  let total_pages = 0;
  let error: string | null = null;
  try {
    const resp = await listNotices({
      q,
      status,
      category,
      bid_type,
      source,
      org_name,
      assignee,
      open_from: toFromIso(open_from),
      open_to: toToIso(open_to),
      close_from: toFromIso(close_from),
      close_to: toToIso(close_to),
      min_base_price,
      max_base_price,
      min_fit_score,
      max_fit_score,
      min_score_total,
      max_score_total,
      has_grade,
      has_documents,
      has_uploads,
      ready_for_submission,
      lifecycle,
      sort,
      direction,
      page,
      page_size,
    });
    items = resp.items;
    total = resp.total ?? items.length;
    total_pages = resp.total_pages ?? 1;
  } catch (e) {
    error = (e as Error).message;
  }

  // 페이지 이동 시 보존할 쿼리 — page만 빼고 모두 복사
  const baseQuery = new URLSearchParams();
  const setStr = (k: string, v: string | undefined) => {
    if (v) baseQuery.set(k, v);
  };
  const setNum = (k: string, v: number | undefined) => {
    if (v !== undefined) baseQuery.set(k, String(v));
  };
  const setBool = (k: string, v: boolean | undefined) => {
    if (v !== undefined) baseQuery.set(k, v ? "true" : "false");
  };
  setStr("q", q);
  status.forEach((v) => baseQuery.append("status", v));
  category.forEach((v) => baseQuery.append("category", v));
  bid_type.forEach((v) => baseQuery.append("bid_type", v));
  source.forEach((v) => baseQuery.append("source", v));
  setStr("org_name", org_name);
  setStr("assignee", assignee);
  setStr("open_from", open_from);
  setStr("open_to", open_to);
  setStr("close_from", close_from);
  setStr("close_to", close_to);
  setNum("min_base_price", min_base_price);
  setNum("max_base_price", max_base_price);
  setNum("min_fit_score", min_fit_score);
  setNum("max_fit_score", max_fit_score);
  setNum("min_score_total", min_score_total);
  setNum("max_score_total", max_score_total);
  setBool("has_grade", has_grade);
  setBool("has_documents", has_documents);
  setBool("has_uploads", has_uploads);
  setBool("ready_for_submission", ready_for_submission);
  baseQuery.set("lifecycle", lifecycle);
  baseQuery.set("sort", sort);
  baseQuery.set("direction", direction);

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-xl font-semibold">공고 목록</h1>
      </section>

      <section>
        <NoticeFilterBar
          q={q}
          status={status}
          category={category}
          bid_type={bid_type}
          source={source}
          org_name={org_name}
          assignee={assignee}
          open_from={open_from}
          open_to={open_to}
          close_from={close_from}
          close_to={close_to}
          min_base_price={min_base_price?.toString()}
          max_base_price={max_base_price?.toString()}
          min_fit_score={min_fit_score?.toString()}
          max_fit_score={max_fit_score?.toString()}
          min_score_total={min_score_total?.toString()}
          max_score_total={max_score_total?.toString()}
          has_grade={has_grade === undefined ? "" : has_grade ? "true" : "false"}
          has_documents={
            has_documents === undefined ? "" : has_documents ? "true" : "false"
          }
          has_uploads={
            has_uploads === undefined ? "" : has_uploads ? "true" : "false"
          }
          ready_for_submission={
            ready_for_submission === undefined
              ? ""
              : ready_for_submission
                ? "true"
                : "false"
          }
          lifecycle={lifecycle}
          sort={sort}
          direction={direction}
          page_size={String(page_size)}
        />
      </section>

      {error ? (
        <div className="rounded border border-red-700 bg-red-950/40 p-4 text-sm">
          <p className="font-semibold text-red-300">API 호출 실패</p>
          <p className="text-slate-300 mt-1">{error}</p>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          조건에 맞는 공고가 없습니다. (필터를 풀거나{" "}
          <Link href="/notices" className="text-brand-400 hover:underline">
            전체 초기화
          </Link>
          )
        </div>
      ) : (
        <>
          <div className="flex justify-between items-center text-xs text-slate-400">
            <Pagination
              page={page}
              totalPages={total_pages}
              total={total}
              pageSize={page_size}
              baseQuery={baseQuery}
            />
          </div>
          <div className="overflow-x-auto rounded border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/80 text-slate-300">
                <tr>
                  <Th>종합</Th>
                  <Th>적합도</Th>
                  <Th>제목</Th>
                  <Th>카테고리</Th>
                  <Th>기관</Th>
                  <Th>예가</Th>
                  <Th>마감</Th>
                  <Th>추천 SKU</Th>
                  <Th>서류</Th>
                  <Th>담당자</Th>
                  <Th>상태</Th>
                  <Th>업데이트</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr
                    key={it.notice_no}
                    className="border-t border-slate-800 hover:bg-slate-900/40"
                  >
                    <Td>
                      <ScoreBadge value={it.score_total} />
                    </Td>
                    <Td>
                      <ScoreBadge value={it.fit_score} mode="0to100" />
                    </Td>
                    <Td>
                      <Link
                        href={`/notices/${encodeURIComponent(it.notice_no)}`}
                        className="text-slate-100 hover:text-brand-500"
                      >
                        {it.title || it.notice_no}
                      </Link>
                    </Td>
                    <Td>
                      <CategoryBadge value={it.category} />
                    </Td>
                    <Td className="text-slate-300">
                      {it.org_name ||
                        ((it.raw as Record<string, unknown> | null)
                          ?.ntceInsttNm as string | undefined) ||
                        "-"}
                    </Td>
                    <Td className="text-slate-300 tabular-nums">
                      {fmtPrice(
                        it.base_price ??
                          ((it.raw as Record<string, unknown> | null)
                            ?.presmptPrce as number | string | null | undefined) ??
                          null,
                      )}
                    </Td>
                    <Td className="text-slate-300 text-xs">
                      {fmtDate(
                        it.close_date ??
                          ((it.raw as Record<string, unknown> | null)
                            ?.bidClseDt as string | null | undefined) ??
                          null,
                      )}
                    </Td>
                    <Td className="text-slate-300">{it.top_sku_name || "-"}</Td>
                    <Td className="text-slate-300 text-xs">
                      {documentSummary(it)}
                    </Td>
                    <Td className="text-slate-300">{it.assignee || "-"}</Td>
                    <Td>
                      <StatusBadge value={it.status} />
                    </Td>
                    <Td className="text-slate-400 text-xs">
                      {fmtDate(it.updated_at)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end items-center text-xs text-slate-400">
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

function Th({ children }: { children: React.ReactNode }) {
  return <th className="text-left font-medium px-3 py-2">{children}</th>;
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

function documentSummary(notice: NoticeRecord): string {
  const docs = readDocumentAutomation(notice);
  return docs ? documentSummaryText(docs) : "-";
}
