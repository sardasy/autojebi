"use client";

import {FileText} from "lucide-react";
import type {SourceDocument} from "@/lib/workspace";
import {buildNoticeBrief, type BriefExcerpt} from "@/lib/noticeBrief";

function Excerpts({items, prefix}: {items: BriefExcerpt[]; prefix: string}) {
  return <ul className="divide-y">{items.map((item,index) => <li key={`${item.documentId}-${index}`} className="py-2 flex gap-3 items-start min-w-0">
    <p className="text-sm leading-6 break-words min-w-0 flex-1">{item.text}</p>
    <a href={`/api/v2${prefix}/documents/${item.documentId}/download`} className="p-2 shrink-0 text-gray-500 hover:text-red-700" title={item.documentName} aria-label={`${item.documentName} 원문 다운로드`}><FileText size={16}/></a>
  </li>)}</ul>;
}

export default function NoticeBrief({documents,prefix}: {documents: SourceDocument[]; prefix:string}) {
  const brief = buildNoticeBrief(documents);
  return <section id="notice-brief" tabIndex={-1} aria-label="공고 핵심 사항" className="grid lg:grid-cols-2 gap-6 items-start min-w-0 scroll-mt-4">
    <div className="border-b pb-3"><h2 className="text-lg font-semibold">제출서류</h2><p className="text-xs text-gray-500 mt-1">원문 발췌 · 준비 여부 미확인</p>
      {brief.submissions.length ? <Excerpts items={brief.submissions} prefix={prefix}/> : <p className="text-sm text-amber-800 py-3">제출서류 목록을 자동 확인하지 못했습니다. 공고 원문과 제안요청서를 확인하세요.</p>}
    </div>
    <div><h2 className="text-lg font-semibold mb-3">주요 사항</h2><dl className="divide-y border-y">{brief.points.map(group => <div key={group.label} className="grid sm:grid-cols-[140px_minmax(0,1fr)] gap-2 sm:gap-5 py-3">
      <dt className="text-sm font-semibold pt-2">{group.label}</dt><dd className="min-w-0">{group.label === "계약·수행 기간" && group.items.length > 1 && <p className="text-xs text-amber-800">기간 조건이 여러 곳에 있습니다. 원문 대조 필요</p>}{group.items.length ? <>
        <Excerpts items={group.items.slice(0,3)} prefix={prefix}/>
        {group.items.length > 3 && <details><summary className="text-sm cursor-pointer text-gray-600 py-2">추가 원문 {group.items.length-3}개</summary><Excerpts items={group.items.slice(3)} prefix={prefix}/></details>}
      </> : <p className="text-sm text-gray-500 py-2">원문 확인 필요</p>}</dd>
    </div>)}</dl></div>
  </section>;
}
