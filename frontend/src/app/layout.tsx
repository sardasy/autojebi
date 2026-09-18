import type { Metadata } from "next";
import Link from "next/link";

import { homePath, isWorkspaceV2Enabled } from "@/lib/flags";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "autojebi · 미림씨스콘 입찰 자동화 콘솔",
  description: "공고 찾기 · 서류 검토 · 비교 작성 · 서류 확인",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen">
        <ToastProvider>
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto max-w-[1440px] px-4 sm:px-6 py-3 flex flex-wrap items-center gap-x-6 gap-y-3">
              <Link href={homePath()} className="text-lg font-semibold text-brand-500">
                autojebi
              </Link>
              <nav aria-label="주 메뉴" className="text-sm text-slate-700 flex flex-wrap gap-4">
                {isWorkspaceV2Enabled() ? <>
                  <Link href="/workspace">공고 찾기</Link>
                  <Link href="/workspace#saved">작성 중 서류</Link>
                </> : <>
                <Link href="/search" className="hover:text-red-700">
                  공고 검색
                </Link>
                <Link href="/reviews">검토함</Link>
                </>}
                <Link href="/admin" className="hover:text-red-700">
                  설정
                </Link>
              </nav>
            </div>
          </header>
          <main className="mx-auto min-w-0 max-w-[1440px] px-4 py-5 sm:px-6">{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
