"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import Link from "next/link";

import { actionSearchG2B, actionUpsertFromSearchResult } from "@/lib/actions";
import type { NoticeSearchItem } from "@/lib/api";
import { useToast } from "./Toast";
import { ActionFeedback } from "./ActionFeedback";

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
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => { setHydrated(true); }, []);

  const runSearch = () => {
    const q = keyword.trim();
    if (!q) {
      setMessage("검색어를 입력하세요"); setError(true);
      toast.push("error", "검색어를 입력하세요");
      return;
    }
    setItems(null); setMessage("G2B 검색 중"); setError(false);
    startSearch(async () => {
      try {
      const r = await actionSearchG2B({ keyword: q, page_size: 30 });
      if (!r.ok) {
        setMessage(`검색 실패: ${r.error}`); setError(true);
        toast.push("error", `검색 실패: ${r.error}`);
        return;
      }
      setItems(r.data.items);
      setMessage(r.data.items.length ? `검색 완료: 총 ${r.data.total}건 · ${r.data.items.length}건 표시` : "검색 결과가 없습니다. 검색어 또는 조회 기간을 바꿔 다시 검색하세요.");
      if (r.data.items.length === 0) toast.push("info", "검색 결과가 없습니다");
      } catch { setMessage("검색 요청에 실패했습니다. 연결 상태를 확인한 뒤 다시 검색하세요."); setError(true); }
    });
  };

  const start = (item: NoticeSearchItem) => {
    setStartingNo(item.notice_no);
    setMessage("공고 저장 중"); setError(false);
    startSearch(async () => {
      try {
        const r = await actionUpsertFromSearchResult(item);
        if (!r.ok) {
          setMessage(`저장 실패: ${r.error}`); setError(true);
          toast.push("error", `시작 실패: ${r.error}`);
          return;
        }
        setItems(current => current?.map(entry => entry.notice_no === item.notice_no ? {...entry, already_exists: true} : entry) || null);
        setMessage("저장 완료. 공고 작업대로 이동합니다.");
        router.push(`/notices/${encodeURIComponent(item.notice_no)}`);
      } catch { setMessage("저장 요청에 실패했습니다. 다시 시도하세요."); setError(true);
      } finally {
        setStartingNo(null);
      }
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="G2B 검색어"
          disabled={!hydrated || searching}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") runSearch();
          }}
          placeholder="공고명·물품명 키워드로 G2B 검색 (예: 변압기 시험기)"
          className="min-w-0 basis-60 flex-1 rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-500"
        />
        <button
          type="button"
          onClick={runSearch}
          disabled={!hydrated || searching}
          className="rounded bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {searching ? "처리 중…" : "G2B 라이브 검색"}
        </button>
      </div>
      <ActionFeedback message={message} error={error}/>

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
              className="flex items-center gap-3 rounded border border-slate-200 bg-slate-50/40 p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-slate-900">
                  {it.title || it.notice_no}
                </div>
                <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-slate-600">
                  <span className="font-mono">{it.notice_no}</span>
                  <span>{it.org_name || "-"}</span>
                  <span>마감 {fmtDate(it.close_date)}</span>
                  <span>{fmtPrice(it.base_price)}</span>
                  {it.already_exists ? (
                    <span className="text-emerald-700">등록됨</span>
                  ) : null}
                </div>
              </div>
              {it.already_exists ? <Link className="work-button shrink-0" href={`/notices/${encodeURIComponent(it.notice_no)}`}>이미 등록 →</Link> : <button
                type="button"
                onClick={() => start(it)}
                disabled={startingNo === it.notice_no}
                className="shrink-0 rounded bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
              >
                {startingNo === it.notice_no ? "저장 중…" : "저장"}
              </button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
