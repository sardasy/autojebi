"use client";
import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { actionProposalStage, actionGetProposalSections } from "@/lib/actions";
import type { ProposalSection } from "@/lib/api";
import { ActionFeedback } from "./ActionFeedback";

const stages = [["analyze", "요구사항 분석"], ["retrieve", "근거 검색"], ["generate", "초안 생성"], ["verify", "사실 검증"]] as const;
export function ProposalActions({ noticeNo }: { noticeNo: string }) {
  const [pending, start] = useTransition();
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sections, setSections] = useState<ProposalSection[]>([]);
  const router = useRouter();
  useEffect(() => {
    let alive = true;
    actionGetProposalSections(noticeNo).then(r => { if (alive) setSections(r.sections); }).catch(() => { if (alive) setMessage("저장된 제안서 섹션을 불러오지 못했습니다. 다시 조회하세요."); });
    return () => { alive = false; };
  }, [noticeNo]);
  return <div><div className="flex flex-wrap gap-2">{stages.map(([stage,label]) => <button key={stage} className="work-button" disabled={pending} onClick={() => {
    setMessage(`${label} 중입니다.`); setError(null);
    start(async () => { try { const result = await actionProposalStage(noticeNo, stage); if (result.sections) setSections(result.sections); setMessage(`${label} 완료`); router.refresh(); } catch(e) { setMessage(`${label} 실패. 이전 단계와 근거 자료를 확인하세요.`); setError((e as Error).message); } });
  }}>{label}</button>)}</div>{message && <ActionFeedback message={message} detail={error} error={Boolean(error)}/>}<div className="divide-y">{sections.map(section => <article className="py-4" key={section.id}><h3 className="font-semibold">{section.section_title}</h3><p className="my-2 text-xs text-amber-800">근거 {section.evidence_ids.length}개 · {section.fact_check_status === "pass" ? "검증 통과" : "검토 필요"} · {section.human_approved ? "승인" : "승인 전"}</p><p className="whitespace-pre-wrap text-sm">{section.generated_content}</p></article>)}</div></div>;
}
