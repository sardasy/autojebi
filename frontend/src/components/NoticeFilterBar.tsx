"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";

import { MultiSelectChips } from "@/components/MultiSelectChips";
import { useToast } from "@/components/Toast";
import { actionCollect } from "@/lib/actions";
import {
  BID_TYPE_OPTIONS,
  CATEGORY_OPTIONS,
  DIRECTION_OPTIONS,
  PAGE_SIZE_OPTIONS,
  PERIOD_QUICK_OPTIONS,
  SORT_OPTIONS,
  SOURCE_OPTIONS,
  STATUS_OPTIONS,
} from "@/lib/constants/notices";

type DateField = "open" | "close";

type Props = {
  q?: string;
  status?: string[];
  category?: string[];
  bid_type?: string[];
  source?: string[];
  org_name?: string;
  assignee?: string;
  open_from?: string;
  open_to?: string;
  close_from?: string;
  close_to?: string;
  min_base_price?: string;
  max_base_price?: string;
  min_fit_score?: string;
  max_fit_score?: string;
  min_score_total?: string;
  max_score_total?: string;
  has_grade?: string;
  has_documents?: string;
  has_uploads?: string;
  ready_for_submission?: string;
  lifecycle?: string;
  sort?: string;
  direction?: string;
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

export function NoticeFilterBar(props: Props) {
  const formRef = useRef<HTMLFormElement>(null);
  const toast = useToast();
  const [pending, startTransition] = useTransition();

  // open_* 값이 URL에 있으면 게시일시 기준, 아니면 마감일시 기준(KJEBI 기본)
  const initialDateField: DateField =
    props.open_from || props.open_to ? "open" : "close";
  const [dateField, setDateField] = useState<DateField>(initialDateField);

  const initialFrom =
    initialDateField === "open"
      ? toDateOnly(props.open_from)
      : toDateOnly(props.close_from);
  const initialTo =
    initialDateField === "open"
      ? toDateOnly(props.open_to)
      : toDateOnly(props.close_to);
  const [periodFrom, setPeriodFrom] = useState(initialFrom);
  const [periodTo, setPeriodTo] = useState(initialTo);

  // 마감 제외 ON ↔ lifecycle=active, OFF ↔ lifecycle=all
  const initialLifecycleOn = (props.lifecycle ?? "active") === "active";
  const [lifecycleOn, setLifecycleOn] = useState(initialLifecycleOn);

  // 펼침 영역 — localStorage에 보존
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    try {
      const saved = localStorage.getItem("notices.filter.expanded");
      if (saved === "1") setExpanded(true);
    } catch {
      // ignore
    }
  }, []);
  const toggleExpanded = () => {
    setExpanded((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("notices.filter.expanded", next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  };

  // 수집 기간 (G2B /collect 트리거 입력 — URL에는 안 들어감)
  const [collectStart, setCollectStart] = useState("");
  const [collectEnd, setCollectEnd] = useState("");

  const navigateWithCurrentFilters = () => {
    const form = formRef.current;
    if (!form) return;
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form).entries()) {
      const text = String(value);
      if (text) params.append(key, text);
    }
    const query = params.toString();
    window.location.assign(query ? `/notices?${query}` : "/notices");
  };

  const applyQuickPeriod = (days: number | null) => {
    if (days === null) {
      setPeriodFrom("");
      setPeriodTo("");
      return;
    }
    const today = new Date();
    if (dateField === "close") {
      setPeriodFrom(fmtDateInput(today));
      setPeriodTo(fmtDateInput(offsetDays(today, days)));
    } else {
      setPeriodFrom(fmtDateInput(offsetDays(today, -days)));
      setPeriodTo(fmtDateInput(today));
    }
  };

  const onSearch = () => {
    if (!collectStart && !collectEnd) {
      navigateWithCurrentFilters();
      return;
    }
    startTransition(async () => {
      try {
        const r = await actionCollect(
          collectStart || undefined,
          collectEnd || undefined,
        );
        toast.push(
          "success",
          `수집 완료 — fetched ${r.fetched}, new ${r.new}, skipped ${r.skipped}`,
        );
      } catch (e) {
        toast.push("error", `수집 실패: ${(e as Error).message}`);
      }
      navigateWithCurrentFilters();
    });
  };

  const lifecycleValue = lifecycleOn ? "active" : "all";

  return (
    <form
      ref={formRef}
      method="get"
      action="/notices"
      className="rounded border border-slate-800 bg-slate-900/40"
    >
      <div className="border-b border-slate-800 px-4 py-2 text-sm font-semibold text-slate-200">
        검색 필터
      </div>

      <div className="space-y-3 px-4 py-3">
        {/* 간편검색 */}
        <div className="flex flex-wrap items-center gap-3">
          <label
            htmlFor="filter-q"
            className="shrink-0 w-24 text-xs text-slate-400"
          >
            ▸ 간편검색
          </label>
          <input
            id="filter-q"
            type="text"
            name="q"
            defaultValue={props.q || ""}
            placeholder="공고명/공고번호/공고기관명/담당자/SKU 입력"
            className="flex-1 min-w-[280px] bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-sm"
          />
        </div>

        {/* 기간 */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="shrink-0 w-24 text-xs text-slate-400">▸ 기간</span>
          <div className="flex items-center gap-3 text-sm">
            <label className="inline-flex items-center gap-1 cursor-pointer text-slate-300">
              <input
                type="radio"
                checked={dateField === "open"}
                onChange={() => setDateField("open")}
                aria-label="게시일시 기준"
              />
              게시일시
            </label>
            <label className="inline-flex items-center gap-1 cursor-pointer text-slate-300">
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
              className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
            />
            <span className="text-slate-500 px-1">부터</span>
            <input
              type="date"
              value={periodTo}
              onChange={(e) => setPeriodTo(e.target.value)}
              aria-label="기간 종료일"
              className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
            />
            <span className="text-slate-500 px-1">까지</span>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {PERIOD_QUICK_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => applyQuickPeriod(o.days)}
                className="rounded border border-slate-700 hover:border-brand-500 px-2 py-0.5 text-xs text-slate-300"
              >
                {o.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400 ml-auto">
            <span>입찰 마감 제외</span>
            <button
              type="button"
              role="switch"
              aria-checked={lifecycleOn}
              aria-label="입찰 마감 제외 토글"
              onClick={() => setLifecycleOn((v) => !v)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${
                lifecycleOn ? "bg-brand-500" : "bg-slate-700"
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition ${
                  lifecycleOn ? "translate-x-5" : "translate-x-1"
                }`}
              />
            </button>
            <span className="text-slate-500">{lifecycleOn ? "ON" : "OFF"}</span>
          </div>
        </div>

        {/* 펼침 토글 */}
        <div className="flex justify-center">
          <button
            type="button"
            onClick={toggleExpanded}
            aria-expanded={expanded}
            aria-controls="filter-advanced"
            className="text-slate-400 hover:text-slate-200 text-sm px-2"
          >
            {expanded ? "▴ 고급 필터 접기" : "▾ 고급 필터 펼치기"}
          </button>
        </div>

        {/* 고급 필터 — DOM에는 항상 존재, expanded=false면 hidden 속성으로 display:none */}
        <div
          id="filter-advanced"
          hidden={!expanded}
          className="space-y-3 border-t border-slate-800 pt-3"
        >
          <FilterRow label="카테고리">
            <MultiSelectChips
              name="category"
              options={CATEGORY_OPTIONS}
              selected={props.category || []}
            />
          </FilterRow>

          <FilterRow label="공고유형">
            <MultiSelectChips
              name="bid_type"
              options={BID_TYPE_OPTIONS}
              selected={props.bid_type || []}
            />
          </FilterRow>

          <FilterRow label="출처">
            <MultiSelectChips
              name="source"
              options={SOURCE_OPTIONS}
              selected={props.source || []}
            />
          </FilterRow>

          <FilterRow label="진행상태">
            <MultiSelectChips
              name="status"
              options={STATUS_OPTIONS}
              selected={props.status || []}
            />
          </FilterRow>

          <FilterRow label="기관 / 담당자">
            <div className="flex flex-wrap gap-2 text-sm">
              <input
                type="text"
                name="org_name"
                defaultValue={props.org_name || ""}
                placeholder="기관명 (부분일치)"
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
              />
              <input
                type="text"
                name="assignee"
                defaultValue={props.assignee || ""}
                placeholder="담당자 (정확일치)"
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
              />
            </div>
          </FilterRow>

          <FilterRow label="예가 (원)">
            <RangeInputs
              fromName="min_base_price"
              toName="max_base_price"
              fromDefault={props.min_base_price}
              toDefault={props.max_base_price}
              step={1}
            />
          </FilterRow>

          <FilterRow label="적합도 (0-100)">
            <RangeInputs
              fromName="min_fit_score"
              toName="max_fit_score"
              fromDefault={props.min_fit_score}
              toDefault={props.max_fit_score}
              min={0}
              max={100}
              step={1}
            />
          </FilterRow>

          <FilterRow label="종합 점수 (0-1)">
            <RangeInputs
              fromName="min_score_total"
              toName="max_score_total"
              fromDefault={props.min_score_total}
              toDefault={props.max_score_total}
              min={0}
              max={1}
              step={0.1}
            />
          </FilterRow>

          <FilterRow label="부가 조건">
            <div className="flex flex-wrap gap-2 text-sm">
              <TriStateSelect
                name="has_grade"
                label="그레이드"
                defaultValue={props.has_grade}
              />
              <TriStateSelect
                name="has_documents"
                label="서류"
                defaultValue={props.has_documents}
              />
              <TriStateSelect
                name="has_uploads"
                label="업로드"
                defaultValue={props.has_uploads}
              />
              <TriStateSelect
                name="ready_for_submission"
                label="제출 준비"
                defaultValue={props.ready_for_submission}
              />
            </div>
          </FilterRow>

          <FilterRow label="정렬 / 페이지">
            <div className="flex flex-wrap gap-2 text-sm">
              <select
                name="sort"
                defaultValue={props.sort || "close_date"}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
                title="정렬"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <select
                name="direction"
                defaultValue={props.direction || "asc"}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
                title="방향"
              >
                {DIRECTION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <select
                name="page_size"
                defaultValue={props.page_size || "20"}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
                title="페이지 크기"
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}개씩
                  </option>
                ))}
              </select>
            </div>
          </FilterRow>

          <FilterRow label="수집 기간 (G2B)">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <input
                type="date"
                value={collectStart}
                onChange={(e) => setCollectStart(e.target.value)}
                aria-label="수집 시작일"
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
              />
              <span className="text-slate-500">~</span>
              <input
                type="date"
                value={collectEnd}
                onChange={(e) => setCollectEnd(e.target.value)}
                aria-label="수집 종료일"
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
              />
              <span className="text-xs text-slate-500">
                비워두면 오늘 날짜만 수집
              </span>
            </div>
          </FilterRow>
        </div>

        {/* 액션 바 */}
        <div className="flex items-center justify-end gap-2 border-t border-slate-800 pt-3">
          <Link
            href="/notices"
            className="rounded border border-slate-700 hover:border-slate-500 px-3 py-1.5 text-sm text-slate-300"
          >
            초기화
          </Link>
          <button
            type="button"
            onClick={onSearch}
            disabled={pending}
            className="rounded bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white"
          >
            {pending ? "수집·조회 중…" : "검색"}
          </button>
        </div>

        {/* URL로 직렬화되는 hidden inputs */}
        <input type="hidden" name="lifecycle" value={lifecycleValue} />
        {dateField === "open" ? (
          <>
            {periodFrom ? (
              <input type="hidden" name="open_from" value={periodFrom} />
            ) : null}
            {periodTo ? (
              <input type="hidden" name="open_to" value={periodTo} />
            ) : null}
          </>
        ) : (
          <>
            {periodFrom ? (
              <input type="hidden" name="close_from" value={periodFrom} />
            ) : null}
            {periodTo ? (
              <input type="hidden" name="close_to" value={periodTo} />
            ) : null}
          </>
        )}
      </div>
    </form>
  );
}

function FilterRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="shrink-0 w-24 text-xs text-slate-400">{label}</span>
      <div className="flex-1 min-w-[280px]">{children}</div>
    </div>
  );
}

function RangeInputs({
  fromName,
  toName,
  fromDefault,
  toDefault,
  min,
  max,
  step,
}: {
  fromName: string;
  toName: string;
  fromDefault?: string;
  toDefault?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <input
        type="number"
        name={fromName}
        defaultValue={fromDefault || ""}
        min={min}
        max={max}
        step={step}
        placeholder="최소"
        className="w-32 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
      />
      <span className="text-slate-500">~</span>
      <input
        type="number"
        name={toName}
        defaultValue={toDefault || ""}
        min={min}
        max={max}
        step={step}
        placeholder="최대"
        className="w-32 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
      />
    </div>
  );
}

function TriStateSelect({
  name,
  label,
  defaultValue,
}: {
  name: string;
  label: string;
  defaultValue?: string;
}) {
  return (
    <label className="inline-flex items-center gap-1 text-xs text-slate-400">
      <span>{label}:</span>
      <select
        name={name}
        defaultValue={defaultValue || ""}
        className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs"
      >
        <option value="">전체</option>
        <option value="true">있음</option>
        <option value="false">없음</option>
      </select>
    </label>
  );
}
