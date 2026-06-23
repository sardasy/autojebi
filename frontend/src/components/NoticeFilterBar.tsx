"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  DEFAULT_DIRECTION,
  DEFAULT_LIFECYCLE,
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT,
  DIRECTION_OPTIONS,
  LIFECYCLE_OPTIONS,
  PAGE_SIZE_OPTIONS,
  PERIOD_QUICK_OPTIONS,
  SORT_OPTIONS,
  STATUS_OPTIONS,
} from "@/lib/constants/notices";

type Mode = "saved" | "g2b";
type DateField = "open" | "close";

type Props = {
  mode?: Mode;
  q?: string;
  status?: string[];
  lifecycle?: string;
  sort?: string;
  direction?: string;
  open_from?: string;
  open_to?: string;
  close_from?: string;
  close_to?: string;
  page_size?: string;
};

function toDateOnly(s: string | undefined): string {
  if (!s) return "";
  return s.slice(0, 10);
}

function offsetDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function fmtDateInput(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function NoticeFilterBar(props: Props) {
  const mode = props.mode || "g2b";
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const initialDateField: DateField =
    props.open_from || props.open_to ? "open" : "close";
  const [dateField, setDateField] = useState<DateField>(initialDateField);
  const [periodFrom, setPeriodFrom] = useState(
    initialDateField === "open"
      ? toDateOnly(props.open_from)
      : toDateOnly(props.close_from),
  );
  const [periodTo, setPeriodTo] = useState(
    initialDateField === "open"
      ? toDateOnly(props.open_to)
      : toDateOnly(props.close_to),
  );

  const applyQuickPeriod = (days: number | null) => {
    if (days === null) {
      setPeriodFrom("");
      setPeriodTo("");
      return;
    }
    const today = new Date();
    setPeriodFrom(fmtDateInput(offsetDays(today, -days)));
    setPeriodTo(fmtDateInput(offsetDays(today, days)));
  };

  // 네이티브 폼 GET은 하드 네비게이션이라 G2B 조회(최대 1~3분) 동안 진행 표시가
  // 전혀 없다. 제출을 가로채 소프트 네비게이션(router.push) + useTransition으로
  // 바꿔서 pending 상태(스피너·배너·상단바)를 노출한다. name 속성은 그대로 두어
  // JS 미동작 환경에서는 기존 GET 폼으로 폴백된다.
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const query = new URLSearchParams();
    for (const [key, value] of formData.entries()) {
      if (typeof value === "string" && value.trim() !== "") {
        query.append(key, value);
      }
    }
    startTransition(() => {
      router.push(`/notices?${query.toString()}`);
    });
  };

  return (
    <form
      method="get"
      action="/notices"
      onSubmit={handleSubmit}
      aria-busy={pending}
      className="overflow-hidden rounded border border-slate-800 bg-slate-900/40"
    >
      {pending ? (
        <div
          role="progressbar"
          aria-label="검색 진행 중"
          className="h-0.5 w-full animate-pulse bg-brand-500"
        />
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-2">
        <div className="text-sm font-semibold text-slate-200">
          {mode === "saved" ? "저장 공고 업무 큐" : "G2B 실시간 검색"}
        </div>
        <div className="flex items-center gap-1 text-xs">
          <Link
            href="/notices?mode=saved"
            className={`rounded px-2 py-1 ${
              mode === "saved"
                ? "bg-brand-500 text-white"
                : "border border-slate-700 text-slate-300 hover:border-brand-500"
            }`}
          >
            저장 공고
          </Link>
          <Link
            href="/notices?mode=g2b"
            className={`rounded px-2 py-1 ${
              mode === "g2b"
                ? "bg-brand-500 text-white"
                : "border border-slate-700 text-slate-300 hover:border-brand-500"
            }`}
          >
            G2B 검색
          </Link>
        </div>
      </div>

      <div className="space-y-3 px-4 py-3">
        <input type="hidden" name="mode" value={mode} />

        <div className="flex flex-wrap items-center gap-3">
          <label
            htmlFor="filter-q"
            className="shrink-0 w-24 text-xs text-slate-400"
          >
            검색어
          </label>
          <input
            id="filter-q"
            type="text"
            name="q"
            defaultValue={props.q || ""}
            placeholder={
              mode === "saved"
                ? "제목, 공고번호, 기관, SKU 검색"
                : "나라장터 공고명 키워드"
            }
            className="flex-1 min-w-[280px] rounded border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm"
          />
        </div>

        {mode === "saved" ? (
          <SavedFilters {...props} />
        ) : (
        <G2BDateFilters
            pageSize={props.page_size}
            dateField={dateField}
            setDateField={setDateField}
            periodFrom={periodFrom}
            setPeriodFrom={setPeriodFrom}
            periodTo={periodTo}
            setPeriodTo={setPeriodTo}
            applyQuickPeriod={applyQuickPeriod}
          />
        )}

        {mode === "saved" ? null : (
          <DateHiddenInputs
            dateField={dateField}
            periodFrom={periodFrom}
            periodTo={periodTo}
          />
        )}

        {pending ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 rounded border border-brand-500/40 bg-brand-500/10 px-3 py-2 text-xs text-brand-200"
          >
            <Spinner className="h-3.5 w-3.5 shrink-0" />
            <span>
              {mode === "g2b"
                ? "나라장터 OpenAPI를 조회하는 중입니다… 기간이 길면 1~3분 걸릴 수 있습니다."
                : "검색 중입니다…"}
            </span>
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-2 border-t border-slate-800 pt-3">
          <Link
            href={mode === "saved" ? "/notices?mode=saved" : "/notices"}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500"
          >
            초기화
          </Link>
          <button
            type="submit"
            disabled={pending}
            aria-busy={pending}
            className="inline-flex items-center gap-2 rounded bg-brand-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? (
              <>
                <Spinner className="h-4 w-4" />
                검색 중…
              </>
            ) : (
              "검색"
            )}
          </button>
        </div>
      </div>
    </form>
  );
}

function SavedFilters(props: Props) {
  const selectedStatus = new Set(props.status || []);
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <span className="shrink-0 w-24 text-xs text-slate-400">상태</span>
        <div className="flex flex-wrap gap-2">
          {STATUS_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="inline-flex items-center gap-1 text-xs text-slate-300"
            >
              <input
                type="checkbox"
                name="status"
                value={option.value}
                defaultChecked={selectedStatus.has(option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="shrink-0 w-24 text-xs text-slate-400" htmlFor="lifecycle">
          진행 상태
        </label>
        <select
          id="lifecycle"
          name="lifecycle"
          defaultValue={props.lifecycle || DEFAULT_LIFECYCLE}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
        >
          {LIFECYCLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <label className="text-xs text-slate-400" htmlFor="sort">
          정렬
        </label>
        <select
          id="sort"
          name="sort"
          defaultValue={props.sort || DEFAULT_SORT}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          name="direction"
          defaultValue={props.direction || DEFAULT_DIRECTION}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
          title="정렬 방향"
        >
          {DIRECTION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <PageSizeSelect pageSize={props.page_size} />
      </div>
    </>
  );
}

function G2BDateFilters({
  pageSize,
  dateField,
  setDateField,
  periodFrom,
  setPeriodFrom,
  periodTo,
  setPeriodTo,
  applyQuickPeriod,
}: {
  pageSize?: string;
  dateField: DateField;
  setDateField: (value: DateField) => void;
  periodFrom: string;
  setPeriodFrom: (value: string) => void;
  periodTo: string;
  setPeriodTo: (value: string) => void;
  applyQuickPeriod: (days: number | null) => void;
}) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <span className="shrink-0 w-24 text-xs text-slate-400">조회 기간</span>
        <div className="flex items-center gap-3 text-sm">
          <label className="inline-flex cursor-pointer items-center gap-1 text-slate-300">
            <input
              type="radio"
              checked={dateField === "open"}
              onChange={() => setDateField("open")}
              aria-label="게시일시 기준"
            />
            게시일시
          </label>
          <label className="inline-flex cursor-pointer items-center gap-1 text-slate-300">
            <input
              type="radio"
              checked={dateField === "close"}
              onChange={() => setDateField("close")}
              aria-label="입찰 마감일시 기준"
            />
            입찰 마감일시
          </label>
        </div>
        <div className="flex items-center gap-1 text-sm">
          <input
            type="date"
            value={periodFrom}
            onChange={(e) => setPeriodFrom(e.target.value)}
            aria-label="기간 시작일"
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
          />
          <span className="px-1 text-slate-500">부터</span>
          <input
            type="date"
            value={periodTo}
            onChange={(e) => setPeriodTo(e.target.value)}
            aria-label="기간 종료일"
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
          />
          <span className="px-1 text-slate-500">까지</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="shrink-0 w-24 text-xs text-slate-400">빠른 기간</span>
        <div className="flex flex-wrap items-center gap-1">
          {PERIOD_QUICK_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => applyQuickPeriod(option.days)}
              className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:border-brand-500"
            >
              {option.label}
            </button>
          ))}
        </div>
        <PageSizeSelect pageSize={pageSize} />
      </div>
    </>
  );
}

function DateHiddenInputs({
  dateField,
  periodFrom,
  periodTo,
}: {
  dateField: DateField;
  periodFrom: string;
  periodTo: string;
}) {
  if (dateField === "open") {
    return (
      <>
        {periodFrom ? <input type="hidden" name="open_from" value={periodFrom} /> : null}
        {periodTo ? <input type="hidden" name="open_to" value={periodTo} /> : null}
      </>
    );
  }
  return (
    <>
      {periodFrom ? <input type="hidden" name="close_from" value={periodFrom} /> : null}
      {periodTo ? <input type="hidden" name="close_to" value={periodTo} /> : null}
    </>
  );
}

function PageSizeSelect({ pageSize }: { pageSize?: string }) {
  return (
    <>
      <label className="text-xs text-slate-400" htmlFor="page_size">
        페이지
      </label>
      <select
        id="page_size"
        name="page_size"
        defaultValue={pageSize || String(DEFAULT_PAGE_SIZE)}
        className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
        title="페이지 크기"
      >
        {PAGE_SIZE_OPTIONS.map((n) => (
          <option key={n} value={n}>
            {n}개씩
          </option>
        ))}
      </select>
    </>
  );
}
