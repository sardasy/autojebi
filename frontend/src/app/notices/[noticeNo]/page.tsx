import Link from "next/link";

import { CategoryBadge } from "@/components/CategoryBadge";
import { BidWorkflowRail } from "@/components/BidWorkflowRail";
import { DocumentPreparationPanel } from "@/components/DocumentPreparationPanel";
import { MetricCard } from "@/components/MetricCard";
import { NoticeActionsBar } from "@/components/NoticeActionsBar";
import { ProposalCoveragePanel } from "@/components/ProposalCoveragePanel";
import { ScoreBadge } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { getNotice, getProposalCoverage, type NoticeRecord, type ProposalCoverageResponse } from "@/lib/api";
import {
  documentSummaryText,
  readDocumentAutomation,
} from "@/lib/documentAutomation";

export const dynamic = "force-dynamic";

function fmt(s: string | null | undefined): string {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleString("ko-KR");
  } catch {
    return s;
  }
}

function fmtPrice(p: number | string | null | undefined): string {
  if (p === null || p === undefined || p === "") return "-";
  const n = typeof p === "string" ? parseFloat(p) : p;
  if (Number.isNaN(n)) return "-";
  return new Intl.NumberFormat("ko-KR").format(n) + "원";
}

export default async function NoticeDetailPage({
  params,
}: {
  params: Promise<{ noticeNo: string }>;
}) {
  const { noticeNo } = await params;
  let notice: NoticeRecord | null = null;
  let error: string | null = null;
  let proposalCoverage: ProposalCoverageResponse | null = null;
  let proposalCoverageError: string | null = null;
  try {
    notice = await getNotice(decodeURIComponent(noticeNo));
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !notice) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="rounded border border-red-700 bg-red-950/40 p-4 text-sm">
          <p className="font-semibold text-red-300">공고를 불러올 수 없습니다</p>
          <p className="mt-1 text-slate-300">{error || "데이터 없음"}</p>
        </div>
      </div>
    );
  }

  const raw = (notice.raw || {}) as Record<string, unknown>;
  const elecSpec = (notice.analysis?.elec_spec || {}) as Record<string, unknown>;
  const grade = (notice.analysis?.grade || {}) as Record<string, unknown>;
  const qualNotes = Array.isArray(grade.qual_notes) ? (grade.qual_notes as string[]) : [];
  const g2bUrl = String(raw.bidNtceDtlUrl || raw.bidNtceUrl || "").trim();
  const docs = readDocumentAutomation(notice);

  try {
    proposalCoverage = await getProposalCoverage(notice.notice_no);
  } catch (e) {
    proposalCoverageError = (e as Error).message;
  }

  return (
    <div className="space-y-6">
      <BackLink />

      <section className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">{notice.title || notice.notice_no}</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <CategoryBadge value={notice.category} />
              <StatusBadge value={notice.status} />
              <ScoreBadge value={notice.score_total} label="종합" />
              <ScoreBadge value={notice.fit_score} mode="0to100" label="fit" />
              <span className="text-slate-400">담당자: {notice.assignee || "-"}</span>
            </div>
          </div>
        </div>
        <div className="text-xs text-slate-500">
          notice_no: <code className="rounded bg-slate-900 px-1">{notice.notice_no}</code>
        </div>
      </section>

      <BidWorkflowRail notice={notice} />

      <section id="work-actions" className="scroll-mt-24">
        <h2 className="mb-2 text-sm font-semibold text-slate-300">작업</h2>
        <NoticeActionsBar notice={notice} />
      </section>

      <section id="grading" className="scroll-mt-24">
        <h2 className="mb-2 text-sm font-semibold text-slate-300">3축 그레이딩</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="사양 (spec)" value={notice.score_spec} />
          <MetricCard label="자격 (qualification)" value={notice.score_qual} />
          <MetricCard label="가격 (price)" value={notice.score_price} />
          <MetricCard label="종합 (total)" value={notice.score_total} />
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card title="추천 SKU">
          {notice.top_sku_name ? (
            <>
              <div className="text-lg font-medium">{notice.top_sku_name}</div>
              <code className="text-xs text-slate-400">{notice.top_sku}</code>
              {notice.sku_match_score !== null ? (
                <div className="mt-2">
                  <ScoreBadge value={notice.sku_match_score} label="유사도" />
                </div>
              ) : null}
            </>
          ) : (
            <span className="text-slate-500">매칭 결과 없음</span>
          )}
        </Card>
        <Card title="적합 사유">
          <p className="whitespace-pre-wrap text-sm text-slate-200">
            {notice.grade_reason || "-"}
          </p>
        </Card>
        <Card title="위험 메모">
          {notice.risk_note ? (
            <p className="whitespace-pre-wrap text-sm text-amber-300">
              {notice.risk_note}
            </p>
          ) : (
            <span className="text-sm text-slate-500">없음</span>
          )}
        </Card>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-300">
          전기 사양 (ElecSpec)
        </h2>
        <Card>
          {Object.keys(elecSpec).length === 0 ? (
            <span className="text-sm text-slate-500">추출된 사양 없음</span>
          ) : (
            <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-3">
              {Object.entries(elecSpec).map(([k, v]) => (
                <Field key={k} label={k}>
                  {Array.isArray(v) ? v.join(", ") : String(v ?? "-")}
                </Field>
              ))}
            </dl>
          )}
        </Card>
      </section>

      {qualNotes.length > 0 ? (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">자격 평가 메모</h2>
          <Card>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-200">
              {qualNotes.map((note, index) => (
                <li key={`${note}-${index}`}>{note}</li>
              ))}
            </ul>
          </Card>
        </section>
      ) : null}

      <section id="documents" className="scroll-mt-24">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-300">서류 준비</h2>
          {docs ? (
            <span className="text-xs text-slate-400">{documentSummaryText(docs)}</span>
          ) : null}
        </div>
        <Card>
          <DocumentPreparationPanel notice={notice} />
        </Card>
      </section>

      <section id="proposal-readiness" className="scroll-mt-24">
        <h2 className="mb-2 text-sm font-semibold text-slate-300">
          제안서 준비도
        </h2>
        <ProposalCoveragePanel
          coverage={proposalCoverage}
          error={proposalCoverageError}
        />
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-300">G2B 메타데이터</h2>
        <Card>
          <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-3">
            <Field label="공고기관">
              {notice.org_name || String(raw.ntceInsttNm || "-")}
            </Field>
            <Field label="수요기관">{String(raw.dminsttNm || "-")}</Field>
            <Field label="입찰방식">{String(raw.bidMethdNm || "-")}</Field>
            <Field label="계약방법">{String(raw.cntrctCnclsMthdNm || "-")}</Field>
            <Field label="예가">
              {fmtPrice(
                notice.base_price ??
                  (raw.presmptPrce as string | number | null | undefined) ??
                  null,
              )}
            </Field>
            <Field label="배정예산">{fmtPrice(raw.asignBdgtAmt as string | number | null)}</Field>
            <Field label="공고일시">
              {fmt(notice.open_date ?? (raw.bidNtceDt as string | undefined) ?? null)}
            </Field>
            <Field label="마감일시">
              {fmt(notice.close_date ?? (raw.bidClseDt as string | undefined) ?? null)}
            </Field>
            <Field label="개찰일시">{fmt(raw.opengDt as string)}</Field>
          </dl>
          {g2bUrl ? (
            <div className="mt-4">
              <a
                href={g2bUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600"
              >
                G2B 원문
              </a>
            </div>
          ) : null}
        </Card>
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/notices" className="text-sm text-slate-400 hover:text-slate-200">
      목록
    </Link>
  );
}

function Card({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2 rounded border border-slate-800 bg-slate-900/40 p-4">
      {title ? (
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          {title}
        </div>
      ) : null}
      <div>{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="break-all text-slate-100">{children}</dd>
    </div>
  );
}
