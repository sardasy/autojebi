"use client";

import { useMemo, useState } from "react";

import type { NoticeRecord, NoticeSpecItem } from "@/lib/api";
import { DEFAULT_COMPANY_NAME } from "@/lib/constants/company";
import { readDocumentAutomation } from "@/lib/documentAutomation";

export interface HwpComposeFormState {
  templatePath: string;
  outputPath: string;
  includeBidForm: boolean;
  includeCompliance: boolean;
  valuesText: string;
}

export interface HwpComposeValidation {
  errors: string[];
  values: Record<string, string>;
}

export function defaultValues(
  notice: NoticeRecord,
  specItems: NoticeSpecItem[],
): Record<string, string> {
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
    company_name: DEFAULT_COMPANY_NAME,
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

/**
 * HwpComposeDialog 폼 상태 훅 — 필드들을 단일 상태 객체로 묶고
 * patch(partial)로 갱신한다. 검증(useMemo)과 기본값 계산도 여기서 수행.
 */
export function useHwpComposeForm(notice: NoticeRecord, specItems: NoticeSpecItem[]) {
  const [form, setForm] = useState<HwpComposeFormState>(() => ({
    templatePath: "templates/입찰참가신청서_양식.hwp",
    outputPath: `output/autofilled_${notice.notice_no}.hwp`,
    includeBidForm: true,
    includeCompliance: true,
    valuesText: JSON.stringify(defaultValues(notice, specItems), null, 2),
  }));

  const patch = (partial: Partial<HwpComposeFormState>) =>
    setForm((prev) => ({ ...prev, ...partial }));

  const validation = useMemo<HwpComposeValidation>(() => {
    const errors: string[] = [];
    if (form.includeBidForm && isUnsafePath(form.templatePath))
      errors.push("template_path 확인 필요");
    if (form.includeBidForm && isUnsafePath(form.outputPath))
      errors.push("output_path 확인 필요");
    let values: Record<string, string> = {};
    try {
      const parsed = form.valuesText.trim() ? JSON.parse(form.valuesText) : {};
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
    if (!form.includeBidForm && !form.includeCompliance)
      errors.push("작성할 HWP 문서를 선택하세요");
    return { errors, values };
  }, [form]);

  return { form, patch, validation };
}
