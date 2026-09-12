"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { NoticeRecord } from "@/lib/api";
import { documentSummaryText, nextNoticeAction, nextNoticeTab, readDocumentAutomation } from "@/lib/documentAutomation";
import { StatusBadge } from "./StatusBadge";
import { ScoreBadge } from "./ScoreBadge";

export function WorkbenchTable({ items }: { items: NoticeRecord[] }) {
  const [score, setScore] = useState(false);
  const [sku, setSku] = useState(false);
  return <section className="min-w-0">
    <div className="mb-2 flex justify-end gap-4 text-xs text-slate-600"><label><input type="checkbox" checked={score} onChange={e => setScore(e.target.checked)}/> 점수</label><label><input type="checkbox" checked={sku} onChange={e => setSku(e.target.checked)}/> 추천 SKU</label></div>
    <div className="overflow-x-auto border-y border-slate-200"><table className="work-table">
      <thead><tr><th>공고명 / 기관</th><th>마감</th><th>상태</th><th>서류 준비</th><th>다음 작업</th>{score && <th>종합점수</th>}{sku && <th>추천 SKU</th>}</tr></thead>
      <tbody>{items.map(notice => {
        const docs = readDocumentAutomation(notice);
        const url = `/notices/${encodeURIComponent(notice.notice_no)}`;
        return <tr key={notice.notice_no} className="hover:bg-slate-50">
          <td className="max-w-sm"><Link href={url} className="font-medium hover:text-red-700 hover:underline">{notice.title || notice.notice_no}</Link><div className="mt-1 text-xs text-slate-500">{notice.org_name || "기관 미확인"} · {notice.notice_no}</div></td>
          <td className="whitespace-nowrap text-xs">{notice.close_date ? new Date(notice.close_date).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "마감 미확인"}</td>
          <td><StatusBadge value={notice.status}/></td>
          <td className="text-xs">{docs ? documentSummaryText(docs) : "서류 분석 전"}<div className="mt-1 text-slate-500">규격 후보 {notice.spec_item_count || 0}개 · 요구값 확인 {notice.spec_value_count || 0}개</div></td>
          <td><Link href={`${url}?tab=${nextNoticeTab(notice)}`} className="inline-flex items-center gap-1 text-sm text-red-700">{nextNoticeAction(notice)}<ArrowRight size={14}/></Link></td>
          {score && <td><ScoreBadge value={notice.score_total}/></td>}{sku && <td>{notice.top_sku_name || notice.top_sku || "미추천"}</td>}
        </tr>;
      })}</tbody>
    </table></div>
  </section>;
}
