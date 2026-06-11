import Link from "next/link";

import { CategoryBadge } from "@/components/CategoryBadge";
import { MetricCard } from "@/components/MetricCard";
import { NoticeActionsBar } from "@/components/NoticeActionsBar";
import { ScoreBadge } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { getNotice, type NoticeRecord } from "@/lib/api";

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
  if (isNaN(n)) return "-";
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
  try {
    notice = await getNotice(decodeURIComponent(noticeNo));
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !notice) {
    return (
      <div className="space-y-4">
        <Link href="/notices" className="text-sm text-slate-400 hover:text-slate-200">
          ← 목록
        </Link>
        <div className="rounded border border-red-700 bg-red-950/40 p-4 text-sm">
          <p className="font-semibold text-red-300">공고를 불러올 수 없습니다</p>
          <p className="text-slate-300 mt-1">{error || "데이터 없음"}</p>
        </div>
      </div>
    );
  }

  const raw = (notice.raw || {}) as Record<string, unknown>;
  const elecSpec = (notice.analysis?.elec_spec || {}) as Record<string, unknown>;
  const grade = (notice.analysis?.grade || {}) as Record<string, unknown>;
  const qualNotes = (grade.qual_notes || []) as string[];
  const g2bUrl = ((raw.bidNtceDtlUrl as string) || (raw.bidNtceUrl as string) || "").trim();

  return (
    <div className="space-y-6">
      <Link href="/notices" className="text-sm text-slate-400 hover:text-slate-200">
        ← 목록
      </Link>

      {/* 헤더 */}
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">{notice.title || notice.notice_no}</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <CategoryBadge value={notice.category} />
          <StatusBadge value={notice.status} />
          <ScoreBadge value={notice.score_total} label="종합" />
          <ScoreBadge value={notice.fit_score} mode="0to100" label="fit" />
          <span className="text-slate-400">담당자: {notice.assignee || "-"}</span>
          <span className="text-slate-500 text-xs ml-auto">
            notice_no: <code className="bg-slate-900 px-1 rounded">{notice.notice_no}</code>
          </span>
        </div>
      </section>

      {/* M8: 액션 바 */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">액션</h2>
        <NoticeActionsBar notice={notice} />
      </section>

      {/* 3축 메트릭 */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">3축 그레이딩</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="사양 (spec)" value={notice.score_spec} />
          <MetricCard label="자격 (qualification)" value={notice.score_qual} />
          <MetricCard label="예가 (price)" value={notice.score_price} />
          <MetricCard label="종합 (total)" value={notice.score_total} />
        </div>
      </section>

      {/* 추천 SKU / 적합 사유 / 위험 노트 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
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
          <p className="text-sm whitespace-pre-wrap text-slate-200">
            {notice.grade_reason || "—"}
          </p>
        </Card>
        <Card title="위험 노트">
          {notice.risk_note ? (
            <p className="text-sm text-amber-300 whitespace-pre-wrap">⚠️ {notice.risk_note}</p>
          ) : (
            <span className="text-slate-500 text-sm">없음</span>
          )}
        </Card>
      </section>

      {/* ElecSpec */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">전기 사양 (ElecSpec)</h2>
        <Card>
          {Object.keys(elecSpec).length === 0 ? (
            <span className="text-slate-500 text-sm">추출된 사양 없음</span>
          ) : (
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
              {Object.entries(elecSpec).map(([k, v]) => (
                <div key={k} className="flex flex-col">
                  <dt className="text-xs text-slate-500">{k}</dt>
                  <dd className="text-slate-100 break-all">
                    {Array.isArray(v) ? v.join(", ") : String(v ?? "—")}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
      </section>

      {/* 자격 메모 */}
      {qualNotes.length > 0 ? (
        <section>
          <h2 className="text-sm font-semibold text-slate-300 mb-2">자격 평가 메모</h2>
          <Card>
            <ul className="list-disc pl-5 text-sm text-slate-200 space-y-1">
              {qualNotes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </Card>
        </section>
      ) : null}

      {/* G2B 메타데이터 */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">G2B 메타데이터</h2>
        <Card>
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
            <Field label="공고기관">
              {notice.org_name || (raw.ntceInsttNm as string) || "-"}
            </Field>
            <Field label="수요기관">{(raw.dminsttNm as string) || "-"}</Field>
            <Field label="입찰방식">{(raw.bidMethdNm as string) || "-"}</Field>
            <Field label="계약방법">{(raw.cntrctCnclsMthdNm as string) || "-"}</Field>
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
                className="inline-block text-sm bg-brand-500 hover:bg-brand-600 text-white px-3 py-1.5 rounded font-medium"
              >
                G2B 원문 →
              </a>
            </div>
          ) : null}
        </Card>
      </section>

    </div>
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
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
      {title ? (
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
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
      <dd className="text-slate-100 break-all">{children}</dd>
    </div>
  );
}
