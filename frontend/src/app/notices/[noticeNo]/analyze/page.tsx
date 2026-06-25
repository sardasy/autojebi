import Link from "next/link";

import { AnalyzeRunner } from "@/components/AnalyzeRunner";
import { RequiredDocsByStage } from "@/components/RequiredDocsByStage";
import { RequiredDocsChecklist } from "@/components/RequiredDocsChecklist";
import { StepNav } from "@/components/StepNav";
import {
  getNotice,
  listRequiredDocuments,
  type NoticeRecord,
  type NoticeRequiredDocument,
} from "@/lib/api";
import { readDocumentAutomation } from "@/lib/documentAutomation";

export const dynamic = "force-dynamic";

export default async function AnalyzeStepPage({
  params,
}: {
  params: Promise<{ noticeNo: string }>;
}) {
  const { noticeNo: rawParam } = await params;
  const noticeNo = decodeURIComponent(rawParam);

  let notice: NoticeRecord | null = null;
  let error: string | null = null;
  try {
    notice = await getNotice(noticeNo);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !notice) {
    return (
      <div>
        <StepNav current="analyze" noticeNo={noticeNo} />
        <div className="rounded border border-rose-800 bg-rose-950/30 p-4 text-sm text-rose-200">
          공고를 불러올 수 없습니다: {error || "데이터 없음"}
        </div>
      </div>
    );
  }

  const docs = readDocumentAutomation(notice);
  const needDocs = docs === null;

  let requiredDocs: NoticeRequiredDocument[];
  try {
    requiredDocs = (await listRequiredDocuments(noticeNo)).items;
  } catch {
    requiredDocs = [];
  }

  const flags = {
    needAnalyze: notice.status === "collected",
    needAttachments: needDocs,
    needDocs,
    needSpec: needDocs,
    needRequiredDocs: requiredDocs.length === 0,
  };

  const requiredItems = (docs?.checklist || []).filter((i) => i.required);
  const readyCount = requiredItems.filter((i) =>
    ["ready", "generated", "not_applicable"].includes(i.status),
  ).length;
  const allReady = requiredItems.length > 0 && readyCount === requiredItems.length;

  return (
    <div>
      <StepNav current="analyze" noticeNo={noticeNo} />
      <h1 className="mb-1 text-xl font-semibold text-slate-100">필요서류분석</h1>
      <p className="mb-5 truncate text-sm text-slate-400">{notice.title || noticeNo}</p>

      <AnalyzeRunner noticeNo={noticeNo} {...flags} />

      <section className="mb-6 space-y-3">
        <h2 className="text-sm font-semibold text-slate-300">
          제출서류 자동확인{" "}
          <span className="text-xs font-normal text-slate-500">
            (첨부문서에서 추출 · 제출시점별 · 사람 확인)
          </span>
        </h2>
        <RequiredDocsByStage noticeNo={noticeNo} items={requiredDocs} />
      </section>

      {docs ? (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">
              회사 준비서류 {readyCount}/{requiredItems.length} 준비
            </h2>
            <Link
              href={`/notices/${encodeURIComponent(noticeNo)}/compose`}
              className={`rounded px-4 py-2 text-sm font-medium ${
                allReady
                  ? "bg-brand-500 text-white hover:bg-brand-600"
                  : "border border-amber-700 bg-amber-950/30 text-amber-200 hover:bg-amber-900/30"
              }`}
            >
              {allReady ? "서류 작성하기 →" : "누락 있어도 작성 진행 →"}
            </Link>
          </div>
          <RequiredDocsChecklist noticeNo={noticeNo} items={docs.checklist} />
        </section>
      ) : (
        <p className="text-sm text-slate-500">
          필요 서류를 분석하는 중입니다. 잠시만 기다려 주세요…
        </p>
      )}
    </div>
  );
}
