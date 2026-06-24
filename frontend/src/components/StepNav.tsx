import Link from "next/link";
import { Fragment } from "react";

type StepKey = "search" | "analyze" | "compose";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "search", label: "공고 검색" },
  { key: "analyze", label: "필요서류분석" },
  { key: "compose", label: "서류작성" },
];

// 3단계 가이드 네비게이션. search는 항상 활성, analyze/compose는 noticeNo가 있을 때만 이동 가능.
export function StepNav({
  current,
  noticeNo,
}: {
  current: StepKey;
  noticeNo?: string;
}) {
  const hrefFor = (key: StepKey): string | null => {
    if (key === "search") return "/search";
    if (!noticeNo) return null;
    return `/notices/${encodeURIComponent(noticeNo)}/${key}`;
  };

  return (
    <nav className="mb-6 flex items-center gap-2 text-sm">
      {STEPS.map((step, idx) => {
        const active = step.key === current;
        const href = hrefFor(step.key);
        const reachable = Boolean(href) && !active;
        const label = (
          <span
            className={`rounded px-3 py-1.5 font-medium ${
              active
                ? "bg-brand-500 text-white"
                : reachable
                  ? "border border-slate-700 text-slate-200 hover:bg-slate-800"
                  : "border border-slate-800 text-slate-500"
            }`}
          >
            {idx + 1}. {step.label}
          </span>
        );
        return (
          <Fragment key={step.key}>
            {reachable && href ? <Link href={href}>{label}</Link> : label}
            {idx < STEPS.length - 1 ? (
              <span className="text-slate-600">›</span>
            ) : null}
          </Fragment>
        );
      })}
      {noticeNo ? (
        <Link
          href={`/notices/${encodeURIComponent(noticeNo)}`}
          className="ml-auto rounded border border-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          고급 보기
        </Link>
      ) : null}
    </nav>
  );
}
