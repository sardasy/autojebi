import Link from "next/link";

/**
 * Next.js 404 fallback — 라우트 매치 실패 시 자동 발동.
 * `notFound()` 호출 또는 `dynamic = "force-dynamic"` 페이지의 throw도 동일하게 처리.
 */
export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="max-w-md rounded border border-slate-800 bg-slate-900/40 p-6 space-y-3 text-center">
        <p className="text-lg font-semibold text-slate-200">페이지를 찾을 수 없습니다</p>
        <p className="text-sm text-slate-400">
          요청한 주소가 잘못됐거나 페이지가 이동·삭제된 것 같습니다.
        </p>
        <Link
          href="/notices"
          className="inline-block rounded bg-brand-500 hover:bg-brand-600 px-4 py-1.5 text-sm font-medium text-white"
        >
          공고 목록으로
        </Link>
      </div>
    </div>
  );
}
