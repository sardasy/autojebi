import type { Metadata } from "next";
import Link from "next/link";

import { ToastProvider } from "@/components/Toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "autojebi · 미림씨스콘 입찰 자동화 콘솔",
  description: "G2B 공고 수집 + 분석 + 3축 그레이딩",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen">
        <ToastProvider>
          <header className="border-b border-slate-800 bg-slate-950">
            <div className="mx-auto max-w-7xl px-6 py-3 flex items-center gap-6">
              <Link href="/search" className="text-lg font-semibold text-brand-500">
                autojebi
              </Link>
              <nav className="text-sm text-slate-300 flex gap-4">
                <Link href="/search" className="hover:text-white">
                  공고 검색
                </Link>
                <Link href="/notices" className="hover:text-white">
                  고급
                </Link>
                <Link href="/admin" className="hover:text-white">
                  어드민
                </Link>
              </nav>
              <span className="ml-auto text-xs text-slate-500">
                API {process.env.NEXT_PUBLIC_API_BASE}
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
