"use client";

import {FileText} from "lucide-react";
import type {SourceDocument} from "@/lib/workspace";
import {buildNoticeBrief, type BriefExcerpt, type BriefGroup, type ServerNoticeBrief} from "@/lib/noticeBrief";

function Excerpts({items, prefix}: {items: BriefExcerpt[]; prefix: string}) {
  return <ul className="divide-y">{items.map((item,index) => <li key={`${item.documentId}-${index}`} className="py-2 flex gap-3 items-start min-w-0">
    <div className="min-w-0 flex-1"><p className="text-sm leading-6 whitespace-pre-wrap break-words max-h-60 overflow-y-auto">{item.quote}</p>{item.locator && <details className="text-xs text-gray-500 break-all"><summary>{item.member_path?.join(" / ") || item.documentName} · 원문 위치</summary>{item.locator}</details>}</div>
    <a href={`/api/v2${prefix}/documents/${item.documentId}/download`} className="p-2 shrink-0 text-gray-500 hover:text-red-700" title={item.documentName} aria-label={`${item.documentName} 원문 다운로드`}><FileText size={16}/></a>
  </li>)}</ul>;
}

function Empty({group}: {group?: BriefGroup}) {
  if (group?.state === "absent_confirmed") return <p className="text-sm py-2">원문에 없음 확인 · {group.absence?.actor?.name || "호환 모드 · 확인자 미기록"} · {group.absence?.created_at}<br/>{group.absence?.scope.map(s => s.name).join(", ")}<br/>{group.absence?.note}</p>;
  return <p className="text-sm text-gray-500 py-2">{group?.state === "incomplete" ? "추출 불완전 · 실패 위치 확인 필요" : "자동 확인 못함 · 원문 확인 필요"}</p>;
}
export default function NoticeBrief({documents,prefix,serverBrief}: {documents: SourceDocument[]; prefix:string; serverBrief?: ServerNoticeBrief}) {
  const brief = serverBrief?.version ? serverBrief : buildNoticeBrief(documents);
  return <section id="notice-brief" tabIndex={-1} aria-label="공고 핵심 사항" className="grid lg:grid-cols-2 gap-6 items-start min-w-0 scroll-mt-4">
    {serverBrief?.review_comparison === "updated" && <p className="lg:col-span-2 text-amber-800">승인 이후 요약 갱신됨 · 원문 승인 유지</p>}
    {serverBrief?.review_comparison === "unavailable" && <p className="lg:col-span-2 text-gray-500">승인 당시 요약 비교 기준 없음</p>}
    {!!serverBrief?.warnings.length && <div className="lg:col-span-2 text-amber-800" role="status"><p>문서 전체 추출 확인 필요</p><ul>{serverBrief.warnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
    <div className="border-b pb-3"><h2 className="text-lg font-semibold">제출서류</h2><p className="text-xs text-gray-500 mt-1">원문 발췌 · 준비 여부 미확인</p>
      {brief.submissions.length ? <Excerpts items={brief.submissions} prefix={prefix}/> : <Empty group={serverBrief?.submission_state}/>}
    </div>
    <div><h2 className="text-lg font-semibold mb-3">주요 사항</h2><dl className="divide-y border-y">{brief.points.map(group => <div key={group.label} className="grid sm:grid-cols-[140px_minmax(0,1fr)] gap-2 sm:gap-5 py-3">
      <dt className="text-sm font-semibold pt-2">{group.label}</dt><dd className="min-w-0">{group.label === "계약·수행 기간" && group.items.length > 1 && <p className="text-xs text-amber-800">기간 조건이 여러 곳에 있습니다. 원문 대조 필요</p>}{group.items.length ? <>
        <Excerpts items={group.items.slice(0,3)} prefix={prefix}/>
        {group.items.length > 3 && <details><summary className="text-sm cursor-pointer text-gray-600 py-2">추가 원문 {group.items.length-3}개</summary><Excerpts items={group.items.slice(3)} prefix={prefix}/></details>}
      </> : <Empty group={serverBrief?.points.find(p => p.label === group.label)}/>}</dd>
    </div>)}</dl></div>
  </section>;
}
