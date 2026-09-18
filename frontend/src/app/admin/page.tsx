import Link from "next/link";
import { isWorkspaceV2Enabled } from "@/lib/flags";
import { DemoReadinessPanel } from "@/components/DemoReadinessPanel";
import { HwpMappingAdmin } from "@/components/HwpMappingAdmin";
import { MailPasteForm } from "@/components/MailPasteForm";
import { SkuIngestButton } from "@/components/SkuIngestButton";
import { UpsertNoticeForm } from "@/components/UpsertNoticeForm";
import WorkspaceLlmStatus from "@/components/WorkspaceLlmStatus";
import CompanyAssets from "@/components/CompanyAssets";
import { getHealth, getHwpAgentHealth, listHwpTemplates, getCompanyProfile } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const documentLoop = isWorkspaceV2Enabled();
  const [health, worker, templates, company] = await Promise.allSettled([getHealth(), getHwpAgentHealth(), listHwpTemplates(), getCompanyProfile()]);
  const hwpTemplates = templates.status === "fulfilled" ? templates.value.items : [];
  const profile = company.status === "fulfilled" ? company.value : null;
  return <div className="space-y-6">
    <h1 className="text-xl font-semibold">{documentLoop ? "서류 작성 설정" : "관리자"}</h1>
    <nav aria-label="관리자 영역" className="flex flex-wrap gap-4 border-b border-slate-200 pb-3 text-sm">{[["connections","연결 상태"],["company","회사정보"],["mappings","HWP 매핑"],...(!documentLoop ? [["sku","SKU 관리"],["manual","공고 등록"]] : [])].map(([id,label]) => <a className="hover:underline" key={id} href={`#${id}`}>{label}</a>)}</nav>
    <section id="connections" className="scroll-mt-4">
      <DemoReadinessPanel health={health.status === "fulfilled" ? health.value : null} healthError={health.status === "rejected" ? "API 연결 실패" : null} hwpHealth={worker.status === "fulfilled" ? worker.value : null} hwpHealthError={worker.status === "rejected" ? "Worker 연결 실패" : null} hwpTemplates={hwpTemplates}/>
      <details className="mt-3 text-xs text-slate-600"><summary>연결 설정</summary><p className="mt-2 break-all">API: {process.env.INTERNAL_API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8001"}</p></details>
      {documentLoop && <WorkspaceLlmStatus/>}
    </section>
    <section id="company" className="work-band scroll-mt-4"><h2 className="mb-4 font-semibold">회사정보</h2>{profile ? <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["회사명",profile.company_name],["사업자번호",profile.business_number],["대표자",profile.ceo_name],["주소",profile.address]].map(([label,value]) => <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 text-sm">{value || "미등록"}</dd></div>)}</dl> : <p role="status" className="text-sm text-red-800">회사정보를 조회하지 못했습니다. API 연결 상태를 확인하세요.</p>}</section>
    <section id="assets" className="work-band scroll-mt-4"><h2 className="mb-4 font-semibold">회사 자료</h2><CompanyAssets/></section>
    <section id="mappings" className="work-band scroll-mt-4"><h2 className="mb-4 font-semibold">HWP 필드 매핑</h2>{templates.status === "fulfilled" ? <HwpMappingAdmin initialTemplates={hwpTemplates}/> : <p role="status" className="text-sm text-red-800">템플릿 조회 실패. 연결 상태를 확인하세요.</p>}</section>
    {!documentLoop && <><section id="sku" className="work-band scroll-mt-4"><h2 className="mb-4 font-semibold">SKU 카탈로그</h2><SkuIngestButton/></section>
    <section id="manual" className="work-band scroll-mt-4"><h2 className="mb-4 font-semibold">공고 수동 Upsert</h2><UpsertNoticeForm/></section>
    <section className="work-band"><h2 className="mb-4 font-semibold">KJEBI 메일 추출</h2><MailPasteForm/></section>
    </>}
    <Link href={documentLoop ? "/workspace" : "/reviews"} className="text-sm text-red-700">{documentLoop ? "서류 작업으로 돌아가기" : "검토함으로 이동"}</Link>
  </div>;
}
