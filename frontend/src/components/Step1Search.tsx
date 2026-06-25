"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { actionSearchG2B, actionUpsertFromSearchResult } from "@/lib/actions";
import type { NoticeSearchItem } from "@/lib/api";
import { useToast } from "./Toast";

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

function fmtPrice(p: number | string | null): string {
  if (p === null || p === undefined || p === "") return "-";
  const n = typeof p === "string" ? parseFloat(p) : p;
  if (Number.isNaN(n)) return "-";
  return new Intl.NumberFormat("ko-KR").format(n) + "원";
}

export function Step1Search() {
  const router = useRouter();
  const toast = useToast();
  const [keyword, setKeyword] = useState("");
  const [items, setItems] = useState<NoticeSearchItem[] | null>(null);
  const [searching, startSearch] = useTransition();
  const [startingNo, setStartingNo] = useState<string | null>(null);

  const runSearch = () => {
    const q = keyword.trim();
    if (!q) {
      toast.push("error", "검색어를 입력하세요");
      return;
    }
    startSearch(async () => {
      const r = await actionSearchG2B({ keyword: q, page_size: 30 });
      if (!r.ok) {
        toast.push("error", `검색 실패: ${r.error}`);
        return;
      }
      setItems(r.data.items);
      if (r.data.items.length === 0) toast.push("info", "검색 결과가 없습니다");
    });
  };

  const start = (item: NoticeSearchItem) => {
    setStartingNo(item.notice_no);
    startSearch(async () => {
      try {
        const r = await actionUpsertFromSearchResult(item);
        if (!r.ok) {
          toast.push("error", `시작 실패: ${r.error}`);
          return;
        }
        router.push(`/notices/${encodeURIComponent(item.notice_no)}/analyze`);
      } finally {
        setStartingNo(null);
      }
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") runSearch();
          }}
          placeholder="공고명·물품명 키워드로 G2B 검색 (예: 변압기 시험기)"
          className="flex-1 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500"
        />
        <button
          type="button"
          onClick={runSearch}
          disabled={searching}
          className="rounded bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {searching ? "검색 중…" : "검색"}
        </button>
      </div>

      {items === null ? (
        <p className="text-sm text-slate-500">
          키워드로 나라장터(G2B) 공고를 검색한 뒤, 처리할 공고를 선택하세요.
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">검색 결과가 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((it) => (
            <li
              key={it.notice_no}
              className="flex items-center gap-3 rounded border border-slate-800 bg-slate-900/40 p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-slate-100">
                  {it.title || it.notice_no}
                </div>
                <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-slate-400">
                  <span className="font-mono">{it.notice_no}</span>
                  <span>{it.org_name || "-"}</span>
                  <span>마감 {fmtDate(it.close_date)}</span>
                  <span>{fmtPrice(it.base_price)}</span>
                  {it.already_exists ? (
                    <span className="text-emerald-300">등록됨</span>
                  ) : null}
                </div>
              </div>
              <button
                type="button"
                onClick={() => start(it)}
                disabled={startingNo === it.notice_no}
                className="shrink-0 rounded bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
              >
                {startingNo === it.notice_no ? "여는 중…" : "이 공고로 시작 →"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
