"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { actionComposeHwpDocuments, actionGetHwpAgentHealth, actionListHwpTemplates, actionPreviewHwpContext } from "@/lib/actions";
import type { HwpComposeRequest, HwpTemplateRecord, NoticeRecord, NoticeSpecItem } from "@/lib/api";
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
    company_name: "",
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
  const [templates, setTemplates] = useState<HwpTemplateRecord[]>([]);
  const [templateKey, setTemplateKey] = useState("bid_form");
  const [previewError, setPreviewError] = useState("");
  const [previewing, setPreviewing] = useState(false);
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
  const [agentDetail, setAgentDetail] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState<string | null>(null);
  const [lastErrors, setLastErrors] = useState<{ stage?: string; detail?: string }[]>([]);
  const [requiredMissing, setRequiredMissing] = useState<string[]>([]);
  const [remainingFields, setRemainingFields] = useState<string[]>([]);
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();

  useEffect(() => {
    if (!open) return;
    let alive = true;
    actionListHwpTemplates().then(result => {
      if (!alive) return;
      const available = result.items.filter(t => t.kind === "bid_form");
      setTemplates(available);
      setTemplateKey(current => available.some(t => t.template_key === current) ? current : available[0]?.template_key || current);
    }).catch(() => { if (alive) setPreviewError("템플릿 목록을 불러오지 못했습니다. 관리자에서 매핑을 확인하세요."); });
    return () => { alive = false; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setPreviewing(true); setPreviewError("");
    actionPreviewHwpContext(notice.notice_no, { template_key: templateKey }).then(result => {
      if (!alive) return;
      setValuesText(JSON.stringify(result.input_values, null, 2));
      setTemplatePath(result.template.template_path);
      setRequiredMissing(result.required_missing);
    }).catch(() => { if (alive) setPreviewError("입력값을 확인하지 못했습니다. 연결 상태와 템플릿 매핑을 확인하세요."); }).finally(() => { if (alive) setPreviewing(false); });
    return () => { alive = false; };
  }, [open, templateKey, notice.notice_no]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setAgentStatus("checking");
    setAgentDetail(null);
    setResultMessage(null);
    setExportPath(null);
    setJobStatus(null);
    setReviewStatus(null);
    setLastErrors([]);
    setRequiredMissing([]);
    setRemainingFields([]);
    actionGetHwpAgentHealth()
      .then((result) => {
        if (alive) {
          setAgentStatus(result.ok ? "ok" : "unavailable");
          setAgentDetail(result.detail || result.base_url || null);
        }
      })
      .catch(() => {
        if (alive) {
          setAgentStatus("unavailable");
          setAgentDetail("HWP Worker 상태 확인 요청에 실패했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const validation = useMemo(() => {
    const errors: string[] = [];
    if (includeBidForm && isUnsafePath(templatePath)) errors.push("template_path 확인 필요");
    if (includeBidForm && isUnsafePath(outputPath)) errors.push("output_path 확인 필요");
    if (includeCompliance && specItems.length === 0) {
      errors.push("규격대응표는 규격 추출 후 생성할 수 있습니다");
    }
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
  }, [includeBidForm, includeCompliance, outputPath, specItems.length, templatePath, valuesText]);

  const currentMissing = jobStatus ? requiredMissing : (templates.find(t => t.template_key === templateKey)?.mappings
    .filter(m => m.active && m.required && !validation.values[m.hwp_field_name]?.trim())
    .map(m => m.hwp_field_name) ?? requiredMissing);

  const submit = () => {
    if (validation.errors.length > 0) {
      toast.push("error", validation.errors.join("\n"));
      return;
    }
    const payload: HwpComposeRequest = {
      template_key: templateKey,
      bid_form_template_path: templatePath,
      bid_form_output_path: outputPath,
      include_bid_form: includeBidForm,
      include_technical_compliance: includeCompliance,
      visible,
      values: validation.values,
    };
    startTransition(async () => {
      try {
        setResultMessage("HWP Worker에 작성 요청을 보냈습니다. 완료되면 결과가 아래에 표시됩니다.");
        setLastErrors([]);
        setRequiredMissing([]);
        setRemainingFields([]);
        setExportPath(null);
        setJobStatus(null);
        setReviewStatus(null);
        const result = await actionComposeHwpDocuments(notice.notice_no, payload);
        const errors = result.errors.length;
        const remaining = result.remaining_placeholders.length;
        const produced = Boolean(result.bid_form || result.technical_compliance);
        setLastErrors(result.errors);
        setRequiredMissing(result.required_missing || []);
        setRemainingFields(result.remaining_placeholders || []);
        setExportPath(
          result.bid_form?.output_path || result.technical_compliance?.output_path || null,
        );
        setJobStatus(result.job?.status || (produced ? "succeeded" : null));
        setReviewStatus(result.job?.review_status || (produced ? "pending" : null));
        router.refresh();
        if ((errors > 0 || result.job?.status === "failed") && !produced) {
          // 사전검증 실패 등 — 아무것도 생성되지 않음. 실제 사유(누락 서류 등)를 노출.
          const reason =
            result.errors
              .map((e) => e.detail)
              .filter(Boolean)
              .join("; ") || result.job?.error_detail || `오류 ${errors}건`;
          const message = `HWP 작성 불가: ${reason}`;
          setResultMessage(message);
          toast.push("error", message);
        } else if (errors > 0) {
          const message = `HWP 작성 일부 완료: 오류 ${errors}건`;
          setResultMessage(message);
          toast.push("info", message);
        } else if (remaining > 0) {
          const message = `HWP 작성 완료: 남은 placeholder ${remaining}개`;
          setResultMessage(message);
          toast.push("info", message);
        } else {
          const message = "HWP 작성 완료";
          setResultMessage(message);
          toast.push("success", message);
        }
      } catch (e) {
        const detail = (e as Error).message;
        setLastErrors([{ stage: "request", detail }]);
        const message = `HWP 작성 실패: ${detail}`;
        setResultMessage(message);
        setJobStatus("failed");
        toast.push("error", message);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="HWP 작성" size="lg">
      <div className="space-y-4">
        <div
          role="status"
          className={`rounded border px-3 py-2 text-xs ${
            agentStatus === "ok"
              ? "border-emerald-800 bg-emerald-50/20 text-emerald-800"
              : agentStatus === "checking"
                ? "border-slate-300 bg-slate-50/50 text-slate-700"
                : "border-amber-800 bg-amber-50/20 text-amber-900"
          }`}
        >
          HWP agent:{" "}
          {agentStatus === "ok"
            ? "연결됨"
            : agentStatus === "checking"
              ? "확인 중"
              : "미연결 또는 비정상"}
          {agentStatus === "unavailable" && <p className="mt-1">Worker를 실행하고 관리자에서 연결 설정을 확인하세요.</p>}
          {agentDetail ? <details className="mt-2 text-slate-600"><summary>기술 상세</summary>{agentDetail}</details> : null}
        </div>

        <label className="block text-sm font-medium">1. 템플릿 선택<select aria-label="HWP 템플릿" className="work-control mt-2 block w-full" value={templateKey} onChange={e => setTemplateKey(e.target.value)} disabled={pending}>
          {!templates.some(t => t.template_key === templateKey) && <option value={templateKey}>입찰참가신청서</option>}
          {templates.map(t => <option key={t.id} value={t.template_key}>{t.name}</option>)}
        </select></label>
        <div><h3 className="mb-2 text-sm font-medium">2. 입력값 확인</h3>
          {previewing && <p role="status" className="text-sm">입력값 확인 중</p>}
          {previewError && <p role="status" className="text-sm text-red-800">{previewError}</p>}
          <div className="grid gap-3 sm:grid-cols-2">{Object.entries(validation.values).map(([key, value]) => <label key={key} className="text-xs text-slate-600">{FIELD_LABELS[key] || key}{templates.find(t => t.template_key === templateKey)?.mappings.some(m => m.hwp_field_name === key && m.required) ? " *" : ""}<input className="work-control mt-1 block w-full" value={value} disabled={pending || previewing} onChange={e => { const values = {...validation.values, [key]: e.target.value}; setValuesText(JSON.stringify(values, null, 2)); setRequiredMissing(templates.find(t => t.template_key === templateKey)?.mappings.filter(m => m.required && !values[m.hwp_field_name]?.trim()).map(m => m.hwp_field_name) || []); }}/></label>)}</div>
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

        <details className="text-sm"><summary className="cursor-pointer">고급 설정</summary>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="block text-xs text-slate-600">
            template_path
            <input
              value={templatePath}
              readOnly
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
            />
          </label>
          <label className="block text-xs text-slate-600">
            output_path
            <input
              value={outputPath}
              onChange={(e) => setOutputPath(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
            />
          </label>
        </div>

        <label className="block text-xs text-slate-600">
          values
          <textarea
            value={valuesText}
            onChange={(e) => setValuesText(e.target.value)}
            rows={9}
            spellCheck={false}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 font-mono text-xs"
          />
        </label>
        </details>

        {validation.errors.length > 0 ? (
          <div className="text-xs text-red-700">{validation.errors.join(", ")}</div>
        ) : null}

        {resultMessage ? (
          <div
            role="status"
            className="rounded border border-slate-300 bg-slate-50/70 p-3 text-sm text-slate-900"
          >
            <div>{resultMessage}</div>
            {exportPath ? (
              <div className="mt-1 text-xs text-slate-600">생성 파일: {exportPath}</div>
            ) : null}
            {jobStatus ? (
              <div className="mt-1 text-xs text-slate-600">
                Job: {jobStatus} · 검토상태: {formatReviewStatus(reviewStatus)}
              </div>
            ) : null}
          </div>
        ) : null}

        {!previewing ? (
          <div className={`p-2 text-xs ${currentMissing.length ? "text-amber-900 bg-amber-50" : "text-slate-600"}`}>
            필수 누락 {currentMissing.length}개: {currentMissing.join(", ")}
          </div>
        ) : null}

        {jobStatus ? (
          <div className={`p-2 text-xs ${remainingFields.length ? "text-amber-900 bg-amber-50" : "text-slate-600"}`}>
            남은 placeholder {remainingFields.length}개: {remainingFields.join(", ")}
          </div>
        ) : null}

        {lastErrors.length > 0 ? (
          <details className="rounded border border-amber-800 bg-amber-50/20 p-3 text-xs text-amber-900">
            <summary className="mb-1 font-semibold">HWP 작성 오류 · 기술 상세</summary>
            <ul className="list-disc space-y-1 pl-4">
              {lastErrors.map((error, index) => (
                <li key={`${error.stage || "error"}-${index}`}>
                  {error.stage ? `${error.stage}: ` : ""}
                  {error.detail || "알 수 없는 오류"}
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={pending || previewing || Boolean(previewError) || validation.errors.length > 0}
            className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "작성 중…" : "작성"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

const FIELD_LABELS: Record<string, string> = { company_name: "회사명", business_number: "사업자번호", ceo_name: "대표자명", address: "주소", notice_no: "공고번호", title: "공고명", notice_title: "공고명", org_name: "기관명", close_date: "마감일", spec_summary: "규격 요약", technical_compliance_summary: "규격 대응 요약", base_price: "기초금액" };

function formatReviewStatus(status: string | null): string {
  if (status === "approved") return "승인";
  if (status === "rejected") return "반려";
  return "검토 대기";
}
