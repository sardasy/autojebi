"use client";

import { useState, useTransition } from "react";

import { actionSearchG2B, actionUpsertFromSearchResult } from "@/lib/actions";
import type { NoticeSearchItem } from "@/lib/api";

import { useToast } from "../Toast";

const PAGE_SIZE = 50;

function todayPlusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * G2BSearchDialog 상태 훅 — 폼 상태(keyword/startDate/endDate)와
 * 검색 결과 상태(items/meta/page/searched/savingNoticeNo)를 분리.
 */
export function useG2BSearch() {
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

  return {
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
  };
}
