"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  actionComposeProposalDocument,
  actionGetHwpAgentHealth,
} from "@/lib/actions";
import type { NoticeRecord, NoticeSpecItem, ProposalComposeRequest } from "@/lib/api";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  notice: NoticeRecord;
  specItems: NoticeSpecItem[];
};

type AgentStatus = "checking" | "ok" | "unavailable";

const PROPOSAL_SECTIONS = [
  "회사 소개",
  "공고 개요",
  "제안 품목",
  "규격 대응 요약",
  "납품/지원 방안",
  "리스크/확인사항",
];

function isUnsafePath(value: string): boolean {
  return Boolean(value) && (value.includes("..") || value.startsWith("/") || /^[A-Za-z]:[\\/]/.test(value));
}

function formatSpecPreview(item: NoticeSpecItem): string {
  const value = item.proposed_value || item.required_value || "값 검토 필요";
  const unit = item.unit && !String(value).includes(item.unit) ? ` ${item.unit}` : "";
  return `${item.label}: ${value}${unit}`;
}

export function ProposalComposeDialog({ open, onClose, notice, specItems }: Props) {
  const [pending, startTransition] = useTransition();
  const [agentStatus, setAgentStatus] = useState<AgentStatus>("checking");
  const [templatePath, setTemplatePath] = useState("templates/제안서_양식.hwp");
  const [visible, setVisible] = useState(false);
  const [overrideJson, setOverrideJson] = useState("{}");
  const [remaining, setRemaining] = useState<string[]>([]);
  const [requiredMissing, setRequiredMissing] = useState<string[]>([]);
  const [errors, setErrors] = useState<{ stage?: string; detail?: string }[]>([]);
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const toast = useToast();
  const router = useRouter();

  const usableItems = useMemo(
    () => specItems.filter((item) => ["candidate", "reviewed", "matched"].includes(item.status)),
    [specItems],
  );

  const reviewWarnings = useMemo(
    () =>
      specItems.filter(
        (item) =>
          item.status === "candidate" ||
          item.status === "gap" ||
          item.review_priority === "high" ||
          item.confidence < 0.75,
      ),
    [specItems],
  );

  const validationErrors = useMemo(() => {
    const result: string[] = [];
    if (isUnsafePath(templatePath)) result.push("template_path 확인 필요");
    return result;
  }, [templatePath]);

  useEffect(() => {
    if (!open) return;
    setAgentStatus("checking");
    setRemaining([]);
    setRequiredMissing([]);
    setErrors([]);
    setExportPath(null);
    setResultMessage(null);
    actionGetHwpAgentHealth()
      .then((result) => setAgentStatus(result.ok ? "ok" : "unavailable"))
      .catch(() => setAgentStatus("unavailable"));
  }, [open]);

  const compose = () => {
    let values_override: Record<string, string>;
    try {
      const parsed = JSON.parse(overrideJson || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("JSON object expected");
      }
      values_override = Object.fromEntries(
        Object.entries(parsed).map(([key, value]) => [key, String(value)]),
      );
    } catch (e) {
      toast.push("error", `override JSON 파싱 실패: ${(e as Error).message}`);
      return;
    }

    const payload: ProposalComposeRequest = {
      template_path: templatePath.trim() || undefined,
      values_override,
      visible,
    };
    setResultMessage(null);
    startTransition(async () => {
      try {
        const result = await actionComposeProposalDocument(notice.notice_no, payload);
        setRemaining(result.remaining_placeholders || []);
        setRequiredMissing(result.required_missing || []);
        setErrors(result.errors || []);
        setExportPath(result.export?.output_path || null);
        router.refresh();
        if (result.export) {
          const message = "제안서 HWP 생성 완료";
          setResultMessage(message);
          toast.push("success", message);
          onClose();
        } else if (result.errors.length > 0) {
          const message = "제안서 HWP 생성 실패: 오류를 확인하세요.";
          setResultMessage(message);
          toast.push("error", message);
        } else {
          const message = "제안서 초안이 저장되었습니다.";
          setResultMessage(message);
          toast.push("info", message);
        }
      } catch (e) {
        setErrors([{ stage: "request", detail: (e as Error).message }]);
        const message = `제안서 작성 실패: ${(e as Error).message}`;
        setResultMessage(message);
        toast.push("error", message);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="제안서 HWP 작성">
      <div className="space-y-3 text-sm">
        <div className="rounded border border-slate-800 bg-slate-950 p-3 text-slate-300">
          HWP agent:{" "}
          {agentStatus === "checking"
            ? "확인 중"
            : agentStatus === "ok"
              ? "연결됨"
              : "미연결 또는 비정상"}
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="block text-xs text-slate-400">
            template_path
            <input
              value={templatePath}
              onChange={(e) => setTemplatePath(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
            />
          </label>
          <label className="inline-flex items-end gap-2 pb-1 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={visible}
              onChange={(e) => setVisible(e.target.checked)}
            />
            HWP 창 표시
          </label>
        </div>

        <div className="grid grid-cols-1 gap-2 rounded border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-300 md:grid-cols-2">
          <div>공고: {notice.title}</div>
          <div>규격 항목: {usableItems.length}개</div>
          <div>추천 SKU: {notice.top_sku_name || notice.top_sku || "검토 필요"}</div>
          <div>기관: {notice.org_name || "-"}</div>
        </div>

        <div className="grid grid-cols-1 gap-3 rounded border border-slate-800 bg-slate-900/40 p-3 md:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold text-slate-300">생성 섹션</div>
            <ul className="space-y-1 text-xs text-slate-400">
              {PROPOSAL_SECTIONS.map((section) => (
                <li key={section}>{section}</li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold text-slate-300">
              규격 대응 샘플
            </div>
            {usableItems.length > 0 ? (
              <ul className="space-y-1 text-xs text-slate-400">
                {usableItems.slice(0, 4).map((item) => (
                  <li key={item.id}>{formatSpecPreview(item)}</li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-slate-500">규격 항목 없음</div>
            )}
          </div>
        </div>

        {reviewWarnings.length > 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-100">
            검토 우선 항목 {reviewWarnings.length}개:{" "}
            {reviewWarnings
              .slice(0, 5)
              .map((item) => item.label)
              .join(", ")}
          </div>
        ) : null}

        {usableItems.length === 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-amber-100">
            규격 추출 필요: 제안서 본문에 사용할 규격 항목이 없습니다.
          </div>
        ) : null}

        {validationErrors.length > 0 ? (
          <div className="text-xs text-red-300">{validationErrors.join(", ")}</div>
        ) : null}

        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-slate-300">override JSON</span>
          <textarea
            value={overrideJson}
            onChange={(e) => setOverrideJson(e.target.value)}
            className="h-36 w-full rounded border border-slate-700 bg-slate-950 p-2 font-mono text-xs text-slate-100"
          />
        </label>

        {exportPath ? (
          <div className="rounded border border-emerald-800 bg-emerald-950/20 p-3 text-emerald-100">
            생성 파일: {exportPath}
          </div>
        ) : null}
        {resultMessage ? (
          <div role="status" className="rounded border border-slate-700 bg-slate-900/70 p-3 text-slate-100">
            {resultMessage}
          </div>
        ) : null}
        {remaining.length > 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-amber-100">
            남은 placeholder {remaining.length}개: {remaining.join(", ")}
          </div>
        ) : null}
        {requiredMissing.length > 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-amber-100">
            필수 누락 {requiredMissing.length}개: {requiredMissing.join(", ")}
          </div>
        ) : null}
        {errors.length > 0 ? (
          <div className="rounded border border-red-900 bg-red-950/30 p-3 text-red-100">
            <div className="mb-1 font-semibold">제안서 작성 오류</div>
            <ul className="list-disc space-y-1 pl-5 text-xs">
              {errors.map((error, index) => (
                <li key={`${error.stage || "error"}-${index}`}>
                  {error.stage ? `${error.stage}: ` : ""}
                  {error.detail || "unknown error"}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-700 px-3 py-2 text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
          <button
            type="button"
            onClick={compose}
            disabled={pending || usableItems.length === 0 || validationErrors.length > 0}
            className="rounded bg-brand-500 px-3 py-2 font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {pending ? "작성 중..." : "작성"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
