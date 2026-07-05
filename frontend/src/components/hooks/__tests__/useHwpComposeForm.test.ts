import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { NoticeRecord, NoticeSpecItem } from "@/lib/api";
import { DEFAULT_COMPANY_NAME } from "@/lib/constants/company";

import { useHwpComposeForm } from "../useHwpComposeForm";

const notice: NoticeRecord = {
  notice_no: "HOOK-1",
  title: "테스트 공고",
  source: "G2B",
  raw: null,
  category: "ABB장비",
  fit_score: 80,
  assignee: "이용문",
  analysis: {},
  status: "analyzed",
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
  bid_no: null,
  bid_seq: null,
  bid_type: null,
  org_code: null,
  org_name: null,
  base_price: null,
  open_date: null,
  close_date: null,
  collected_at: null,
  score_spec: null,
  score_qual: null,
  score_price: null,
  score_total: null,
  grade_reason: null,
  risk_note: null,
  top_sku: null,
  top_sku_name: null,
  sku_match_score: null,
  graded_at: null,
};

const specItems: NoticeSpecItem[] = [
  {
    id: 1,
    notice_no: "HOOK-1",
    item_key: "rated_voltage",
    label: "정격전압",
    required_value: "22.9",
    proposed_value: "22.9kV 대응",
    unit: "kV",
    category: "technical",
    source: "rule",
    confidence: 0.8,
    evidence: {},
    status: "matched",
    sort_order: 1,
    created_at: null,
    updated_at: null,
  },
];

describe("useHwpComposeForm", () => {
  it("initializes defaults with company name and notice-scoped output path", () => {
    const { result } = renderHook(() => useHwpComposeForm(notice, specItems));

    expect(result.current.form.templatePath).toBe("templates/입찰참가신청서_양식.hwp");
    expect(result.current.form.outputPath).toBe("output/autofilled_HOOK-1.hwp");
    expect(result.current.form.includeBidForm).toBe(true);
    expect(result.current.form.includeCompliance).toBe(true);
    expect(result.current.validation.errors).toEqual([]);
    expect(result.current.validation.values.company_name).toBe(DEFAULT_COMPANY_NAME);
    expect(result.current.validation.values.spec_summary).toContain("정격전압: 22.9kV 대응 kV");
  });

  it("patch merges partial state and validation reacts to it", () => {
    const { result } = renderHook(() => useHwpComposeForm(notice, specItems));

    act(() => result.current.patch({ valuesText: "{not json" }));
    expect(
      result.current.validation.errors.some((e) => e.startsWith("JSON 파싱 실패")),
    ).toBe(true);
    // 다른 필드는 유지
    expect(result.current.form.outputPath).toBe("output/autofilled_HOOK-1.hwp");

    act(() =>
      result.current.patch({
        valuesText: "{}",
        includeBidForm: false,
        includeCompliance: false,
      }),
    );
    expect(result.current.validation.errors).toEqual(["작성할 HWP 문서를 선택하세요"]);
  });
});
