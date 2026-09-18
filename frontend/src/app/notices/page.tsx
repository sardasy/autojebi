import { redirect } from "next/navigation";

import { isWorkspaceV2Enabled } from "@/lib/flags";

export const dynamic = "force-dynamic";

export default function NoticesPage() {
  if (isWorkspaceV2Enabled()) redirect("/workspace");

  // Retiring the legacy list does not enable the validation workspace in production.
  return (
    <section className="space-y-3">
      <h1 className="text-xl font-semibold">기존 공고 목록 화면이 종료되었습니다</h1>
      <p className="text-sm text-slate-600">
        공고와 작성 서류는 보존되어 있습니다. 서류 작업은 별도로 실행한 검토 작업대를 이용해 주세요.
      </p>
    </section>
  );
}
