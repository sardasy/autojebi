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
  type RequiredDocsStopPoint,
} from "@/lib/api";
import { readDocumentAutomation } from "@/lib/documentAutomation";

export const dynamic = "force-dynamic";

const STOP_MESSAGE: Record<RequiredDocsStopPoint, string> = {
  no_uploads: "첨부 미수집 — 공고에 첨부가 없거나 아직 가져오지 못했습니다.",
  no_text: "첨부 텍스트 추출 실패 — 스캔본/이미지 PDF이거나 추출이 어려운 문서입니다.",
  no_candidates: "제출서류 후보 0건 — 첨부 본문에서 제출서류 키워드를 찾지 못했습니다.",
  no_classification: "LLM 분류 0건 — 후보는 있었으나 제출서류로 분류되지 않았습니다.",
  ok: "",
};

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
  let stopPoint: RequiredDocsStopPoint | null;
  try {
    const res = await listRequiredDocuments(noticeNo);
    requiredDocs = res.items;
    stopPoint = res.diagnostics?.stopped_at ?? null;
  } catch {
    requiredDocs = [];
    stopPoint = null;
  }

  const flags = {
    needAnalyze: notice.status === "collected",
    needAttachments: needDocs,
    needDocs,
    needSpec: needDocs,
    needRequiredDocs: requiredDocs.length === 0,
  };

  // 1순위 — 공고 원문 제출서류 카운트 (requirement_type=required 기준 확인율)
  const officialRequired = requiredDocs.filter((d) => d.requirement_type === "required");
  const officialChecked = officialRequired.filter((d) => d.checked).length;

  // 2순위 — 회사 보조 후보 카운트 (격하)
  const checklist = docs?.checklist || [];
  const commonItems = checklist.filter(
    (i) => i.type === "company_common" || i.document_role === "internal_prep",
  );
  const confirmItems = checklist.filter(
    (i) =>
      i.document_role !== "reference_only" &&
      !(i.type === "company_common" || i.document_role === "internal_prep"),
  );
  const readyOf = (arr: typeof checklist) =>
    arr.filter((i) => ["ready", "generated"].includes(i.status)).length;

  return (
    <div>
      <StepNav current="analyze" noticeNo={noticeNo} />
      <h1 className="mb-1 text-xl font-semibold text-slate-100">필요서류분석</h1>
      <p className="mb-5 truncate text-sm text-slate-400">{notice.title || noticeNo}</p>

      <AnalyzeRunner noticeNo={noticeNo} {...flags} />

      {/* 1순위: 공고 원문 제출서류 — 권위 있는 기준 */}
      <section className="mb-6 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">
            공고 원문 제출서류{" "}
            <span className="text-xs font-normal text-slate-500">
              (첨부 원문에서 추출 · 제출시점별)
            </span>
          </h2>
          <span className="text-xs text-slate-400">
            확인 {officialChecked}/{officialRequired.length}
          </span>
        </div>
        {requiredDocs.length === 0 && stopPoint && stopPoint !== "ok" ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-100">
            공고 원문에서 제출서류를 확정하지 못했습니다 — {STOP_MESSAGE[stopPoint]}
          </div>
        ) : (
          <RequiredDocsByStage noticeNo={noticeNo} items={requiredDocs} />
        )}
      </section>

      {/* 2순위(격하): 회사 보조 준비 후보 */}
      {docs ? (
        <section className="space-y-3 rounded border border-slate-800 bg-slate-950/40 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-300">
                회사 공통 후보 · 보조 준비서류
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                공고 필수가 아니라 회사가 보통 준비하는 보조 목록입니다 · 회사 공통{" "}
                {readyOf(commonItems)}/{commonItems.length} · 추가 확인{" "}
                {readyOf(confirmItems)}/{confirmItems.length}
              </p>
            </div>
            <Link
              href={`/notices/${encodeURIComponent(noticeNo)}/compose`}
              className="shrink-0 rounded bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              서류 작성하기 →
            </Link>
          </div>
          <RequiredDocsChecklist noticeNo={noticeNo} items={checklist} />
        </section>
      ) : (
        <p className="text-sm text-slate-500">
          필요 서류를 분석하는 중입니다. 잠시만 기다려 주세요…
        </p>
      )}
    </div>
  );
}
