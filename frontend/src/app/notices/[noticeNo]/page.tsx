import Link from "next/link";
import { NoticeWorkspace } from "@/components/NoticeWorkspace";
import { getNotice, getProposalCoverage } from "@/lib/api";

export const dynamic = "force-dynamic";
export default async function NoticeDetailPage({ params }: { params: Promise<{ noticeNo: string }> }) {
  const { noticeNo } = await params;
  let notice;
  try { notice = await getNotice(decodeURIComponent(noticeNo)); }
  catch { return <div role="alert"><h1 className="text-xl font-semibold">공고를 불러올 수 없습니다</h1><p className="my-3">연결 상태와 공고번호를 확인한 뒤 다시 시도하세요.</p><Link href="/notices">공고 작업대</Link></div>; }
  let coverage = null;
  let coverageError = null;
  try { coverage = await getProposalCoverage(notice.notice_no); } catch (e) { coverageError = (e as Error).message; }
  return <NoticeWorkspace notice={notice} coverage={coverage} coverageError={coverageError}/>;
}
