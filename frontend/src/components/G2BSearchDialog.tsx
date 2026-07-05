"use client";

import Link from "next/link";
import { useState } from "react";

import type { NoticeSearchItem } from "@/lib/api";

import { useG2BSearch } from "./hooks/useG2BSearch";
import { Modal } from "./Modal";

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

function hasG2BAttachment(item: NoticeSearchItem): boolean {
  return Object.entries(item.raw || {}).some(
    ([key, value]) =>
      key.startsWith("ntceSpecDocUrl") &&
      typeof value === "string" &&
      value.trim().length > 0,
  );
}

export function G2BSearchDialog() {
  const [open, setOpen] = useState(false);
  const {
    keyword,
    setKeyword,
    startDate,
    setStartDate,
    endDate,
    setEndDate,
    items,
    searched,
    savingNoticeNo,
    searching,
    page,
    meta,
    reset,
    fetchPage,
    search,
    save,
  } = useG2BSearch();

  const close = () => {
    setOpen(false);
    reset();
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
                    <th className="text-left font-medium px-3 py-2">첨부</th>
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
                      <td className="px-3 py-2">
                        {hasG2BAttachment(it) ? (
                          <span className="rounded border border-cyan-700 bg-cyan-950/40 px-2 py-1 text-xs text-cyan-200">
                            있음
                          </span>
                        ) : (
                          <span className="text-xs text-slate-500">없음</span>
                        )}
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
