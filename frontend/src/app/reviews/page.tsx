import Link from "next/link";
import { listHwpJobs } from "@/lib/api";
import { HwpJobs } from "@/components/DocumentPreparationPanel";

export const dynamic = "force-dynamic";

export default async function ReviewsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const str = (key: string) => typeof params[key] === "string" ? params[key] as string : "";
  const review = str("review_status");
  const status = str("status");
  const q = str("q");
  const page = Math.max(1, Number(str("page")) || 1);
  const filters = { q, review_status: ["pending", "approved", "rejected"].includes(review) ? review : "", status: ["pending", "running", "completed", "failed"].includes(status) ? status : "", page };
  let result;
  try { result = await listHwpJobs(filters); } catch { return <div role="status" className="work-band text-red-800">검토 목록을 불러오지 못했습니다. 관리자에서 API 연결 상태를 확인한 뒤 새로고침하세요.</div>; }
  const href = (p: number) => `/reviews?${new URLSearchParams({ q, review_status: filters.review_status, status: filters.status, page: String(p) })}`;
  return <div className="space-y-5">
    <h1 className="text-xl font-semibold">검토함</h1>
    <form className="flex flex-wrap items-end gap-3" action="/reviews">
      <label className="text-sm">공고 검색<input name="q" defaultValue={q} className="work-control mt-1 block" placeholder="공고명 또는 공고번호"/></label>
      <label className="text-sm">검토 상태<select name="review_status" defaultValue={filters.review_status} className="work-control mt-1 block"><option value="">전체</option><option value="pending">검토 대기</option><option value="approved">승인</option><option value="rejected">반려</option></select></label>
      <label className="text-sm">생성 상태<select name="status" defaultValue={filters.status} className="work-control mt-1 block"><option value="">전체</option><option value="completed">생성 성공</option><option value="failed">생성 실패</option><option value="pending">대기</option><option value="running">처리 중</option></select></label>
      <button className="work-button">조회</button>
    </form>
    <p role="status" className="text-sm text-slate-600">총 {result.total}건</p>
    {result.items.length === 0 && <p className="work-band text-sm text-slate-600">조건에 맞는 생성 기록이 없습니다.</p>}
    {result.items.map(item => <section key={item.job.id} className="work-band">
      <h2 className="mb-2 font-semibold"><Link href={`/notices/${encodeURIComponent(item.job.notice_no)}?tab=exports`} className="hover:underline">{item.title || item.job.notice_no}</Link></h2>
      <p className="mb-3 text-xs text-slate-500">{item.job.notice_no} · {item.template_name || "템플릿 미확인"}</p>
      <HwpJobs noticeNo={item.job.notice_no} jobs={[item.job]} exports={item.export ? [item.export] : []}/>
    </section>)}
    {result.total_pages > 1 && <nav aria-label="검토함 페이지" className="flex items-center gap-3">{page > 1 && <Link className="work-button" href={href(page-1)}>이전</Link>}<span>{page} / {result.total_pages}</span>{page < result.total_pages && <Link className="work-button" href={href(page+1)}>다음</Link>}</nav>}
  </div>;
}
