"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { actionSearchG2B, actionUpsertFromSearchResult } from "@/lib/actions";
import type { NoticeSearchItem } from "@/lib/api";

import { Modal } from "./Modal";
import { useToast } from "./Toast";

/**
 * M13 — G2B 라이브 검색 다이얼로그.
 *
 * 흐름:
 *   1. 키워드 + (선택) 날짜 범위 → POST /notices/search
 *   2. 결과 테이블: already_exists=true는 상세 링크, false는 저장 버튼
 *   3. 저장 성공 시 해당 행만 already_exists=true로 갱신 (재검색 X)
 */

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

function fmtPrice(p: number | null): string {
  if (p === null || p === undefined) return "-";
  return new Intl.NumberFormat("ko-KR").format(p) + "원";
}

function todayPlusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

const PAGE_SIZE = 50;

export function G2BSearchDialog() {
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [startDate, setStartDate] = useState(todayPlusDays(-30));
  const [endDate, setEndDate] = useState(todayPlusDays(30));
  const [items, setItems] = useState<NoticeSearchItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [savingNoticeNo, setSavingNoticeNo] = useState<string | null>(null);
  const [searching, startSearchTransition] = useTransition();
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState<{ total: number; total_pages: number } | null>(
    null,
  );
  const toast = useToast();

  const reset = () => {
    setItems([]);
    setSearched(false);
    setSavingNoticeNo(null);
    setPage(1);
    setMeta(null);
  };

  const close = () => {
    setOpen(false);
    reset();
  };

  // 동일 키워드·날짜로 임의 페이지 페치. 새 검색은 search() (page=1 리셋).
  const fetchPage = (targetPage: number) => {
    const kw = keyword.trim();
    if (!kw) {
      toast.push("error", "키워드를 입력하세요");
      return;
    }
    startSearchTransition(async () => {
      const r = await actionSearchG2B({
        keyword: kw,
        start_date: startDate ? `${startDate}T00:00:00` : undefined,
        end_date: endDate ? `${endDate}T23:59:59` : undefined,
        page: targetPage,
        page_size: PAGE_SIZE,
      });
      if (!r.ok) {
        toast.push("error", `G2B 검색 실패: ${r.error}`);
        setItems([]);
        setSearched(true);
        return;
      }
      setItems(r.data.items);
      setSearched(true);
      setPage(r.data.page);
      setMeta({ total: r.data.total, total_pages: r.data.total_pages });
    });
  };

  const search = () => {
    setPage(1);
    fetchPage(1);
  };

  const save = async (item: NoticeSearchItem) => {
    setSavingNoticeNo(item.notice_no);
    try {
      const r = await actionUpsertFromSearchResult(item);
      if (!r.ok) {
        toast.push("error", `저장 실패: ${r.error}`);
        return;
      }
      setItems((prev) =>
        prev.map((it) =>
          it.notice_no === item.notice_no ? { ...it, already_exists: true } : it,
        ),
      );
      toast.push("success", `${item.notice_no} 저장 완료`);
    } finally {
      setSavingNoticeNo(null);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded border border-slate-700 hover:border-brand-500 px-3 py-1.5 text-sm text-slate-200"
      >
        G2B 라이브 검색
      </button>

      <Modal open={open} onClose={close} title="G2B 라이브 검색" size="lg">
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-2">
            <label className="block flex-1 min-w-[200px]">
              <span className="mb-1 block text-xs text-slate-400">키워드</span>
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") search();
                }}
                placeholder="예: ABB 차단기"
                className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-slate-400">시작일</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-slate-400">종료일</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm"
              />
            </label>
            <button
              type="button"
              onClick={search}
              disabled={searching}
              className="rounded bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {searching ? "검색 중… (긴 기간은 1~3분 소요)" : "검색"}
            </button>
          </div>

          {searched && items.length === 0 && !searching ? (
            <div className="rounded border border-slate-800 bg-slate-900/40 p-4 text-center text-sm text-slate-400">
              G2B 검색 결과가 없습니다.
            </div>
          ) : null}

          {meta && meta.total > 0 ? (
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>
                총 {meta.total.toLocaleString("ko-KR")}건 · {page} / {meta.total_pages} 페이지
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => fetchPage(page - 1)}
                  disabled={page <= 1}
                  className="rounded border border-slate-700 hover:border-brand-500 px-2 py-1 disabled:opacity-30"
                >
                  ← 이전
                </button>
                <button
                  type="button"
                  onClick={() => fetchPage(page + 1)}
                  disabled={page >= meta.total_pages}
                  className="rounded border border-slate-700 hover:border-brand-500 px-2 py-1 disabled:opacity-30"
                >
                  다음 →
                </button>
              </div>
            </div>
          ) : null}

          {items.length > 0 ? (
            <div className="overflow-x-auto rounded border border-slate-800 max-h-[55vh]">
              <table className="w-full text-sm">
                <thead className="bg-slate-900/80 text-slate-300 sticky top-0">
                  <tr>
                    <th className="text-left font-medium px-3 py-2">공고번호</th>
                    <th className="text-left font-medium px-3 py-2">제목</th>
                    <th className="text-left font-medium px-3 py-2">기관</th>
                    <th className="text-right font-medium px-3 py-2">예가</th>
                    <th className="text-left font-medium px-3 py-2">마감</th>
                    <th className="text-right font-medium px-3 py-2">액션</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <tr
                      key={it.notice_no}
                      className="border-t border-slate-800 hover:bg-slate-900/40"
                    >
                      <td className="px-3 py-2 font-mono text-xs text-slate-300">
                        {it.notice_no}
                      </td>
                      <td className="px-3 py-2 text-slate-100">{it.title}</td>
                      <td className="px-3 py-2 text-slate-300">
                        {it.org_name || "-"}
                      </td>
                      <td className="px-3 py-2 text-right text-slate-300 tabular-nums">
                        {fmtPrice(it.base_price)}
                      </td>
                      <td className="px-3 py-2 text-slate-300 text-xs">
                        {fmtDate(it.close_date)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {it.already_exists ? (
                          <Link
                            href={`/notices/${encodeURIComponent(it.notice_no)}`}
                            className="rounded border border-emerald-700 bg-emerald-950/50 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-900/50"
                          >
                            이미 등록 →
                          </Link>
                        ) : (
                          <button
                            type="button"
                            onClick={() => save(it)}
                            disabled={savingNoticeNo === it.notice_no}
                            className="rounded bg-brand-500 hover:bg-brand-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                          >
                            {savingNoticeNo === it.notice_no
                              ? "저장 중…"
                              : "저장"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>
              기본 기간 오늘 ±30일. 최대 365일까지 검색 가능 (긴 기간은 1~3분 소요). 저장 시 source=G2B로 즉시 등록됩니다.
            </span>
            <button
              type="button"
              onClick={close}
              className="text-slate-400 hover:text-slate-200"
            >
              닫기
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
