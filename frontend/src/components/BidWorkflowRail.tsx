import type { NoticeRecord } from "@/lib/api";
import { bidWorkflowSteps, nextNoticeAction } from "@/lib/documentAutomation";

const STATE_CLASS = {
  done: "border-emerald-700 bg-emerald-950/30 text-emerald-100",
  current: "border-brand-500 bg-brand-950/40 text-brand-100",
  pending: "border-slate-800 bg-slate-900/40 text-slate-400",
  blocked: "border-red-800 bg-red-950/30 text-red-100",
};

const STATE_LABEL = {
  done: "완료",
  current: "진행",
  pending: "대기",
  blocked: "막힘",
};

const STEP_TARGET: Record<ReturnType<typeof bidWorkflowSteps>[number]["id"], string> = {
  review: "#work-actions",
  documents: "#documents",
  spec: "#spec-items",
  compliance: "#spec-items",
  proposal: "#spec-items",
};

const STEP_ACTION_LABEL: Record<ReturnType<typeof bidWorkflowSteps>[number]["id"], string> = {
  review: "분석/그레이드로 이동",
  documents: "서류 준비로 이동",
  spec: "규격 항목으로 이동",
  compliance: "규격대응표 작성으로 이동",
  proposal: "제안서 작성으로 이동",
};

type Props = {
  notice: NoticeRecord;
};

export function BidWorkflowRail({ notice }: Props) {
  const steps = bidWorkflowSteps(notice);
  return (
    <section className="rounded border border-slate-800 bg-slate-900/35 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">입찰 업무 흐름</h2>
          <p className="mt-1 text-xs text-slate-500">
            공고 검토에서 제안서 초안까지 현재 처리 위치를 표시합니다.
          </p>
        </div>
        <div className="rounded border border-brand-700 bg-brand-950/30 px-3 py-1.5 text-sm text-brand-100">
          다음 작업: <span className="font-semibold">{nextNoticeAction(notice)}</span>
        </div>
      </div>
      <ol className="grid grid-cols-1 gap-2 md:grid-cols-5">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className={`rounded border px-3 py-2 ${STATE_CLASS[step.state]}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-slate-500">{index + 1}</span>
              <span className="rounded bg-slate-950/40 px-2 py-0.5 text-[11px]">
                {STATE_LABEL[step.state]}
              </span>
            </div>
            <div className="mt-2 text-sm font-semibold">{step.label}</div>
            <div className="mt-1 min-h-8 text-xs opacity-80">{step.detail}</div>
            <a
              href={STEP_TARGET[step.id]}
              className="mt-3 inline-flex text-xs font-medium text-slate-200 underline decoration-slate-600 underline-offset-4 hover:text-white"
            >
              {STEP_ACTION_LABEL[step.id]}
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}
