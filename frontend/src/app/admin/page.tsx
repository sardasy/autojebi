import Link from "next/link";

import { MailPasteForm } from "@/components/MailPasteForm";
import { SkuIngestButton } from "@/components/SkuIngestButton";
import { UpsertNoticeForm } from "@/components/UpsertNoticeForm";

export const dynamic = "force-dynamic";

export default function AdminPage() {
  return (
    <div className="space-y-8">
      <Link href="/notices" className="text-sm text-slate-400 hover:text-slate-200">
        ← 공고 목록
      </Link>

      <div className="space-y-1">
        <h1 className="text-xl font-semibold">어드민</h1>
        <p className="text-xs text-amber-400">
          ⚠ 내부 네트워크 전용 — X-API-Key는 Server Action에서 자동 첨부. 사용자/세션 인증은 후속 마일스톤에서 별도 검토.
        </p>
      </div>

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <h2 className="text-base font-semibold text-slate-100">공고 수동 Upsert</h2>
        <p className="text-xs text-slate-400">
          KJEBI 메일 경로 / 테스트 데이터 / 누락된 공고 보강에 사용. status는{" "}
          <code className="bg-slate-800 px-1 rounded">collected</code>로 시작.
        </p>
        <UpsertNoticeForm />
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <h2 className="text-base font-semibold text-slate-100">KJEBI 메일 추출 (M12)</h2>
        <p className="text-xs text-slate-400">
          KJEBI 알림메일 본문을 paste하면 Claude가 공고번호·제목·마감·예가를 추출해{" "}
          <code className="rounded bg-slate-800 px-1">POST /notices/extract-from-mail</code>로
          자동 등록합니다. <code className="rounded bg-slate-800 px-1">notice_no</code>가 잡히지
          않으면 등록은 건너뛰고 추출 결과만 표시.
        </p>
        <MailPasteForm />
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <h2 className="text-base font-semibold text-slate-100">SKU 카탈로그 인제스트</h2>
        <p className="text-xs text-slate-400">
          Qdrant 컬렉션 <code className="bg-slate-800 px-1 rounded">abb_skus</code>를
          채움. 카탈로그 변경 시 재실행. 1회 호출이면 충분.
        </p>
        <SkuIngestButton />
      </section>
    </div>
  );
}
