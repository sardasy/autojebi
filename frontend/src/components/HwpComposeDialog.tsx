"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { actionComposeHwpDocuments, actionGetHwpAgentHealth } from "@/lib/actions";
import type { HwpComposeRequest, NoticeRecord, NoticeSpecItem } from "@/lib/api";
import { readDocumentAutomation } from "@/lib/documentAutomation";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  notice: NoticeRecord;
  specItems: NoticeSpecItem[];
};

function defaultValues(notice: NoticeRecord, specItems: NoticeSpecItem[]): Record<string, string> {
  const docs = readDocumentAutomation(notice);
  const draft = docs?.drafts?.bid_form_values;
  const draftValues =
    draft && typeof draft === "object" && !Array.isArray(draft)
      ? (draft as Record<string, unknown>).values
      : null;
  const specs = specItems
    .filter((item) => item.status !== "ignored")
    .map((item) => {
      const value = item.proposed_value || item.required_value || "";
      const unit = item.unit ? ` ${item.unit}` : "";
      return value ? `${item.label}: ${value}${unit}` : "";
    })
    .filter(Boolean)
    .join("; ");
  return {
    company_name: "미림씨스콘",
    business_number: "",
    ceo_name: "",
    address: "",
    ...(draftValues && typeof draftValues === "object" && !Array.isArray(draftValues)
      ? Object.fromEntries(
          Object.entries(draftValues as Record<string, unknown>).map(([key, value]) => [
            key,
            String(value ?? ""),
          ]),
        )
      : {}),
    spec_summary: specs,
    technical_compliance_summary: specs,
  };
}

function isUnsafePath(value: string): boolean {
  return !value || value.includes("..") || value.startsWith("/") || /^[A-Za-z]:[\\/]/.test(value);
}

export function HwpComposeDialog({ open, onClose, notice, specItems }: Props) {
  const [templatePath, setTemplatePath] = useState("templates/입찰참가신청서_양식.hwp");
  const [outputPath, setOutputPath] = useState(`output/autofilled_${notice.notice_no}.hwp`);
  const [includeBidForm, setIncludeBidForm] = useState(true);
  const [includeCompliance, setIncludeCompliance] = useState(true);
  const [visible, setVisible] = useState(false);
  const [valuesText, setValuesText] = useState(
    JSON.stringify(defaultValues(notice, specItems), null, 2),
  );
  const [agentStatus, setAgentStatus] = useState<"checking" | "ok" | "unavailable">(
    "checking",
  );
  const [lastErrors, setLastErrors] = useState<{ stage?: string; detail?: string }[]>([]);
  const [requiredMissing, setRequiredMissing] = useState<string[]>([]);
  const [remainingFields, setRemainingFields] = useState<string[]>([]);
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setAgentStatus("checking");
    actionGetHwpAgentHealth()
      .then((result) => {
        if (alive) setAgentStatus(result.ok ? "ok" : "unavailable");
      })
      .catch(() => {
        if (alive) setAgentStatus("unavailable");
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const validation = useMemo(() => {
    const errors: string[] = [];
    if (includeBidForm && isUnsafePath(templatePath)) errors.push("template_path 확인 필요");
    if (includeBidForm && isUnsafePath(outputPath)) errors.push("output_path 확인 필요");
    let values: Record<string, string> = {};
    try {
      const parsed = valuesText.trim() ? JSON.parse(valuesText) : {};
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        errors.push("values는 JSON 객체여야 합니다");
      } else {
        values = Object.fromEntries(
          Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [
            key,
            String(value ?? ""),
          ]),
        );
      }
    } catch (e) {
      errors.push(`JSON 파싱 실패: ${(e as Error).message}`);
    }
    if (!includeBidForm && !includeCompliance) errors.push("작성할 HWP 문서를 선택하세요");
    return { errors, values };
  }, [includeBidForm, includeCompliance, outputPath, templatePath, valuesText]);

  const submit = () => {
    if (validation.errors.length > 0) {
      toast.push("error", validation.errors.join("\n"));
      return;
    }
    const payload: HwpComposeRequest = {
      bid_form_template_path: templatePath,
      bid_form_output_path: outputPath,
      include_bid_form: includeBidForm,
      include_technical_compliance: includeCompliance,
      visible,
      values: validation.values,
    };
    startTransition(async () => {
      try {
        const result = await actionComposeHwpDocuments(notice.notice_no, payload);
        const errors = result.errors.length;
        const remaining = result.remaining_placeholders.length;
        setLastErrors(result.errors);
        setRequiredMissing(result.required_missing || []);
        setRemainingFields(result.remaining_placeholders || []);
        router.refresh();
        if (errors > 0) {
          toast.push("info", `HWP 작성 일부 완료: 오류 ${errors}건`);
        } else if (remaining > 0) {
          toast.push("info", `HWP 작성 완료: 남은 입력값 ${remaining}개`);
          onClose();
        } else {
          toast.push("success", "HWP 작성 완료");
          onClose();
        }
      } catch (e) {
        const detail = (e as Error).message;
        setLastErrors([{ stage: "request", detail }]);
        toast.push("error", `HWP 작성 실패: ${detail}`);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="HWP 작성" size="lg">
      <div className="space-y-4">
        <div
          className={`rounded border px-3 py-2 text-xs ${
            agentStatus === "ok"
              ? "border-emerald-800 bg-emerald-950/20 text-emerald-100"
              : agentStatus === "checking"
                ? "border-slate-700 bg-slate-900/50 text-slate-300"
                : "border-amber-800 bg-amber-950/20 text-amber-100"
          }`}
        >
          HWP agent:{" "}
          {agentStatus === "ok"
            ? "연결됨"
            : agentStatus === "checking"
              ? "확인 중"
              : "미연결 또는 비정상"}
        </div>

        <div className="flex flex-wrap gap-4 text-sm">
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeBidForm}
              onChange={(e) => setIncludeBidForm(e.target.checked)}
            />
            입찰참가신청서
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeCompliance}
              onChange={(e) => setIncludeCompliance(e.target.checked)}
            />
            규격대응표
          </label>
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
            HWP 창 표시
          </label>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="block text-xs text-slate-400">
            template_path
            <input
              value={templatePath}
              onChange={(e) => setTemplatePath(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="block text-xs text-slate-400">
            output_path
            <input
              value={outputPath}
              onChange={(e) => setOutputPath(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm"
            />
          </label>
        </div>

        <label className="block text-xs text-slate-400">
          values
          <textarea
            value={valuesText}
            onChange={(e) => setValuesText(e.target.value)}
            rows={9}
            spellCheck={false}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs"
          />
        </label>

        {validation.errors.length > 0 ? (
          <div className="text-xs text-red-300">{validation.errors.join(", ")}</div>
        ) : null}

        {requiredMissing.length > 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-100">
            필수 누락 {requiredMissing.length}개: {requiredMissing.join(", ")}
          </div>
        ) : null}

        {remainingFields.length > 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-100">
            남은 placeholder {remainingFields.length}개: {remainingFields.join(", ")}
          </div>
        ) : null}

        {lastErrors.length > 0 ? (
          <div className="rounded border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-100">
            <div className="mb-1 font-semibold">HWP 작성 오류</div>
            <ul className="list-disc space-y-1 pl-4">
              {lastErrors.map((error, index) => (
                <li key={`${error.stage || "error"}-${index}`}>
                  {error.stage ? `${error.stage}: ` : ""}
                  {error.detail || "알 수 없는 오류"}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-300"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={pending || validation.errors.length > 0 || specItems.length === 0}
            className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "작성 중…" : "작성"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
