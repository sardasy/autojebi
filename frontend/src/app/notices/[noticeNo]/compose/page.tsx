import { ComposeStep } from "@/components/ComposeStep";
import { StepNav } from "@/components/StepNav";
import { getNotice, type ExportRecord, type NoticeRecord } from "@/lib/api";
import { readDocumentAutomation } from "@/lib/documentAutomation";

export const dynamic = "force-dynamic";

export default async function ComposeStepPage({
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
        <StepNav current="compose" noticeNo={noticeNo} />
        <div className="rounded border border-rose-800 bg-rose-950/30 p-4 text-sm text-rose-200">
          공고를 불러올 수 없습니다: {error || "데이터 없음"}
        </div>
      </div>
    );
  }

  const docs = readDocumentAutomation(notice);
  const exports: ExportRecord[] = docs?.exports || [];

  return (
    <div>
      <StepNav current="compose" noticeNo={noticeNo} />
      <h1 className="mb-1 text-xl font-semibold text-slate-100">서류작성</h1>
      <p className="mb-5 truncate text-sm text-slate-400">{notice.title || noticeNo}</p>

      <ComposeStep noticeNo={noticeNo} exports={exports} />
    </div>
  );
}
