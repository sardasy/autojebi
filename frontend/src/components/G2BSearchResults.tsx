"use client";

import Link from "next/link";
import { useState } from "react";

import { actionUpsertFromSearchResult } from "@/lib/actions";
import type { NoticeSearchItem } from "@/lib/api";
import { useToast } from "./Toast";

type Props = {
  items: NoticeSearchItem[];
};

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
  if (Number.isNaN(n)) return "-";
  return new Intl.NumberFormat("ko-KR").format(n) + "원";
}

function hasG2BAttachment(item: NoticeSearchItem): boolean {
  return Object.entries(item.raw || {}).some(
    ([key, value]) =>
      key.startsWith("ntceSpecDocUrl") &&
      typeof value === "string" &&
      value.trim().length > 0,
  );
}

export function G2BSearchResults({ items }: Props) {
  const [rows, setRows] = useState(items);
  const [savingNoticeNo, setSavingNoticeNo] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const toast = useToast();

  const save = async (item: NoticeSearchItem) => {
    setSavingNoticeNo(item.notice_no);
    setResultMessage(`${item.notice_no} 저장 중입니다.`);
    try {
      const r = await actionUpsertFromSearchResult(item);
      if (!r.ok) {
        const message = `저장 실패: ${r.error}`;
        setResultMessage(message);
        toast.push("error", message);
        return;
      }
      setRows((prev) =>
        prev.map((row) =>
          row.notice_no === item.notice_no ? { ...row, already_exists: true } : row,
        ),
      );
      const message = `${item.notice_no} 저장 완료. 상세 화면에서 분석을 시작할 수 있습니다.`;
      setResultMessage(message);
      toast.push("success", message);
    } finally {
      setSavingNoticeNo(null);
    }
  };

  return (
    <div className="space-y-3">
      {resultMessage ? (
        <div role="status" className="rounded border border-slate-300 bg-slate-50/70 p-3 text-sm text-slate-900">
          {resultMessage}
        </div>
      ) : null}
      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/80 text-slate-700">
            <tr>
              <Th>공고번호</Th>
              <Th>제목</Th>
              <Th>기관</Th>
              <Th>예가</Th>
              <Th>게시</Th>
              <Th>마감</Th>
              <Th>첨부</Th>
              <Th>등록 상태</Th>
              <Th>작업</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((it) => (
              <tr
                key={it.notice_no}
                className="border-t border-slate-200 hover:bg-slate-50/40"
              >
                <Td className="font-mono text-xs text-slate-700">{it.notice_no}</Td>
                <Td>
                  {it.already_exists ? (
                    <Link
                      href={`/notices/${encodeURIComponent(it.notice_no)}`}
                      className="text-slate-900 hover:text-brand-500"
                    >
                      {it.title || it.notice_no}
                    </Link>
                  ) : (
                    <span className="text-slate-900">{it.title || it.notice_no}</span>
                  )}
                </Td>
                <Td className="text-slate-700">{it.org_name || "-"}</Td>
                <Td className="tabular-nums text-slate-700">{fmtPrice(it.base_price)}</Td>
                <Td className="text-xs text-slate-700">{fmtDate(it.open_date)}</Td>
                <Td className="text-xs text-slate-700">{fmtDate(it.close_date)}</Td>
                <Td>
                  {hasG2BAttachment(it) ? (
                    <span className="rounded border border-cyan-700 bg-cyan-950/40 px-2 py-1 text-xs text-cyan-200">
                      있음
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">없음</span>
                  )}
                </Td>
                <Td>
                  {it.already_exists ? (
                    <span className="rounded border border-emerald-700 bg-emerald-50/50 px-2 py-1 text-xs text-emerald-800">
                      등록됨
                    </span>
                  ) : (
                    <span className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700">
                      신규
                    </span>
                  )}
                </Td>
                <Td>
                  {it.already_exists ? (
                    <Link
                      href={`/notices/${encodeURIComponent(it.notice_no)}`}
                      className="rounded border border-emerald-700 bg-emerald-50/50 px-2 py-1 text-xs text-emerald-800 hover:bg-emerald-900/50"
                    >
                      상세로 이동
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={() => save(it)}
                      disabled={savingNoticeNo === it.notice_no}
                      className="rounded bg-brand-500 px-2 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
                    >
                      {savingNoticeNo === it.notice_no ? "저장 중" : "저장"}
                    </button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
