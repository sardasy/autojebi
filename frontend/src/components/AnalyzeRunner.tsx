"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  actionAnalyze,
  actionAnalyzeDocuments,
  actionExtractSpecItems,
  actionFetchG2BAttachments,
} from "@/lib/actions";

type Props = {
  noticeNo: string;
  needAnalyze: boolean;
  needAttachments: boolean;
  needDocs: boolean;
  needSpec: boolean;
};

// 필요서류분석 자동 실행기. 마운트 시 1회, 누락된 단계만 순차 실행하고 끝나면 페이지를
// 새로고침해 결과(체크리스트)를 보여준다. 반복/중복 호출은 ref 가드 + 누락분 한정으로 방지.
export function AnalyzeRunner({
  noticeNo,
  needAnalyze,
  needAttachments,
  needDocs,
  needSpec,
}: Props) {
  const router = useRouter();
  const started = useRef(false);
  const [step, setStep] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const anyNeeded = needAnalyze || needAttachments || needDocs || needSpec;

  useEffect(() => {
    if (!anyNeeded || started.current) return;
    started.current = true;
    (async () => {
      try {
        if (needAnalyze) {
          setStep("공고 분석 중…");
          await actionAnalyze(noticeNo);
        }
        if (needAttachments) {
          setStep("첨부 서류 수집 중…");
          await actionFetchG2BAttachments(noticeNo);
        }
        if (needDocs || needAttachments) {
          setStep("필요 서류 판정 중…");
          await actionAnalyzeDocuments(noticeNo);
        }
        if (needSpec) {
          setStep("규격 항목 추출 중…");
          await actionExtractSpecItems(noticeNo);
        }
        setStep(null);
        router.refresh();
      } catch (e) {
        setError((e as Error).message);
        setStep(null);
      }
    })();
  }, [anyNeeded, needAnalyze, needAttachments, needDocs, needSpec, noticeNo, router]);

  if (error) {
    return (
      <div className="mb-4 rounded border border-rose-800 bg-rose-950/30 p-3 text-sm text-rose-200">
        자동 분석 중 오류: {error}
      </div>
    );
  }
  if (step) {
    return (
      <div className="mb-4 flex items-center gap-3 rounded border border-slate-700 bg-slate-900/50 p-3 text-sm text-slate-200">
        <span className="h-3 w-3 animate-pulse rounded-full bg-brand-500" />
        {step}
      </div>
    );
  }
  return null;
}
