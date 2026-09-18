"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, Plus } from "lucide-react";
import { Workspace, workspaceApi } from "@/lib/workspace";
import type { NoticeSearchItem } from "@/lib/api";
import { deadlineState } from "@/lib/deadline";

export default function WorkspacesPage() {
  const [items, setItems] = useState<{notice_no: string; title: string; workspace: Workspace | null}[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<NoticeSearchItem[]>([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [searchError, setSearchError] = useState(false);
  const [keyword, setKeyword] = useState("");
  async function searchG2b() {
    if (!keyword.trim() || busy) return;
    setBusy(true); setResults([]); setSearchError(false); setStatus("G2B 검색 중");
    try {const result = await workspaceApi<{items: typeof results; total: number}>("/search", {keyword: keyword.trim()}); setResults(result.items); setStatus(result.total ? `G2B 검색 결과 ${result.total}건` : "검색 결과가 없습니다. 검색어를 바꿔 다시 검색하세요.");}
    catch(e) {setSearchError(true); setStatus((e as Error).message);} finally {setBusy(false);}
  }
  async function refresh(next = page) {
    try { const result = await workspaceApi<{items: typeof items; has_more: boolean}>(`/notices?q=${encodeURIComponent(q)}&page=${next}`);
      setItems(result.items); setMore(result.has_more); setPage(next);
    } catch (e) {setStatus((e as Error).message);}
  }
  useEffect(() => {void refresh(1);}, []);
  async function register(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const closeDate = String(form.get("close_date") || "");
      await workspaceApi("/notices", {notice_no: form.get("notice_no"), title: form.get("title"), source: "MANUAL",
        org_name: String(form.get("org_name") || "") || null,
        close_date: closeDate ? `${closeDate}:00+09:00` : null, raw: {}});
      setStatus("공고 등록 완료"); await refresh(1);
    } catch(e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="space-y-5 min-w-0">
    <h1 className="text-2xl font-semibold">1. 공고 찾기</h1>
    <section className="border-y py-3" aria-label="나라장터 검색">
      <form className="flex flex-wrap gap-2 mt-3" onSubmit={e => {e.preventDefault(); void searchG2b();}}><input aria-label="G2B 공고명" required disabled={busy} value={keyword} onChange={e => setKeyword(e.target.value)} className="border p-2 min-w-0 flex-1"/><button disabled={busy} className="border px-3 py-2 text-sm whitespace-nowrap">{busy ? "처리 중" : "G2B 라이브 검색"}</button></form>
      <label className="flex gap-2 items-center text-sm py-3"><input type="checkbox" checked={openOnly} onChange={e => setOpenOnly(e.target.checked)}/>마감 전 공고만</label>
      <p role="status" className={`text-sm break-words pb-3 ${searchError ? "text-red-700" : "text-gray-700"}`}>{status}</p>
      {!!results.length && <p className="text-sm pb-2">불러온 결과 {results.length}건 · 필터 후 표시 {results.filter(r => !openOnly || deadlineState(r.close_date) === "마감 전").length}건</p>}
      {openOnly && results.length > 0 && !results.some(r => deadlineState(r.close_date) === "마감 전") && <p className="text-sm text-amber-800 py-2">검색 결과 중 마감 전으로 확인된 공고가 없습니다. 전체 결과에서 마감·미확인 공고를 확인할 수 있습니다.</p>}
      {results.filter(result => !openOnly || deadlineState(result.close_date) === "마감 전").map(result => <div key={result.notice_no} className="border-t py-3 text-sm flex flex-wrap justify-between gap-2"><div className="min-w-0 flex-1 basis-60"><strong className="break-words">{result.title}</strong><p className="text-gray-600 mt-1">{result.org_name || "기관 미확인"} · {result.notice_no}</p><p className={deadlineState(result.close_date) === "마감 전" ? "text-green-800" : "text-amber-800"}>{deadlineState(result.close_date)} · {result.close_date && Number.isFinite(Date.parse(result.close_date)) ? new Date(result.close_date).toLocaleString("ko-KR", {timeZone:"Asia/Seoul"}) : "일시 확인 필요"}</p></div>{result.already_exists ? <Link href={`/workspace/${result.notice_no}`} className="underline self-center">이미 등록 →</Link> : <button className="self-center border rounded px-3 py-2" disabled={busy} onClick={async () => {setBusy(true); setSearchError(false); try {await workspaceApi("/notices", {...result, already_exists: undefined, source: "G2B"}); setResults(old => old.map(r => r.notice_no === result.notice_no ? {...r, already_exists: true} : r)); setStatus("저장 완료"); await refresh(1);} catch(e) {setSearchError(true); setStatus((e as Error).message);} finally {setBusy(false);}}}>저장</button>}</div>)}
    </section>
    <h2 id="saved" className="text-lg font-semibold">작성 중 서류</h2>
    <form className="flex gap-2" onSubmit={e => {e.preventDefault(); void refresh(1);}}>
      <input aria-label="공고 검색" value={q} onChange={e => setQ(e.target.value)} className="border p-2 min-w-0" />
      <button type="submit" title="공고 검색" aria-label="공고 검색 실행" className="border p-2"><Search size={20}/></button>
    </form>
    <div className="overflow-x-auto border-y">
      <table className="w-full text-sm text-left"><thead className="bg-gray-100"><tr>{["공고", "작성 상태", "확인 필요", "다음 작업"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead>
        <tbody>{items.map(item => <tr key={item.notice_no} className="border-t"><td className="p-3 min-w-52"><Link className="text-red-700 underline" href={`/workspace/${encodeURIComponent(item.notice_no)}`}>{item.title || item.notice_no}</Link><div className="text-gray-500 text-xs">{item.notice_no}</div></td>
          <td className="p-3 whitespace-nowrap">{item.workspace?.ready ? "확인 완료" : item.workspace?.inputs.proposal_sections?.length ? "초안 검토" : "서류 검토"}</td><td className="p-3">{item.workspace?.blockers.length ?? "미확인"}</td><td className="p-3 min-w-44">{item.workspace?.next_action || "원문 검토 시작"}</td></tr>)}</tbody>
      </table>
    </div>
    <div className="flex gap-3"><button disabled={page <= 1} onClick={() => void refresh(page-1)}>이전</button><span>{page}</span><button disabled={!more} onClick={() => void refresh(page+1)}>다음</button></div>
    <details className="border-t pt-3"><summary>공고 수동 등록</summary><form className="flex flex-wrap gap-3 mt-3" onSubmit={register}>
      <label>공고번호<input name="notice_no" required className="block border p-2"/></label><label>공고명<input name="title" required className="block border p-2"/></label>
      <label>공고 기관<input name="org_name" className="block border p-2"/></label>
      <label>입찰 마감일시 (한국시간)<input name="close_date" type="datetime-local" step="60" className="block border p-2"/></label>
      <p className="basis-full text-sm text-gray-600">공식 공고에서 확인한 마감일시를 입력하세요. 미입력 시 검토용 작성은 가능하며 제출 준비 완료는 제한됩니다.</p>
      <button disabled={busy} className="flex gap-1 items-center"><Plus size={18}/>등록</button>
    </form></details>
  </div>;
}
