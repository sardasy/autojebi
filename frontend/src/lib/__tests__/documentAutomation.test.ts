import { describe, expect, it } from "vitest";

import type {
  DocumentAutomationResult,
  DocumentChecklistItem,
  NoticeRecord,
} from "../api";
import {
  bidWorkflowSteps,
  documentSummaryText,
  nextNoticeAction,
  readDocumentAutomation,
} from "../documentAutomation";

function mkItem(
  partial: Partial<DocumentChecklistItem> & { id: string },
): DocumentChecklistItem {
  return {
    name: partial.name ?? partial.id,
    type: partial.type ?? "other",
    required: partial.required ?? true,
    status: partial.status ?? "needed",
    owner: partial.owner ?? null,
    reason: partial.reason ?? null,
    source: partial.source ?? "rule",
    due_hint: partial.due_hint ?? null,
    note: partial.note ?? null,
    ...partial,
  };
}

function mkNotice(
  analysis: Record<string, unknown> | null,
  overrides: Partial<NoticeRecord> = {},
): NoticeRecord {
  return {
    notice_no: "T1",
    title: "t",
    source: "TEST",
    raw: null,
    category: "ABB장비",
    fit_score: 0,
    assignee: "x",
    analysis: (analysis ?? {}) as Record<string, unknown>,
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
    unresolved_error_count: 0,
    export_count: 0,
    spec_item_count: 0,
    ...overrides,
  };
}

describe("readDocumentAutomation", () => {
  it("returns null when analysis.document_automation is missing", () => {
    expect(readDocumentAutomation(mkNotice({}))).toBeNull();
  });

  it("returns null when document_automation is not a plain object", () => {
    expect(
      readDocumentAutomation(mkNotice({ document_automation: [] })),
    ).toBeNull();
    expect(
      readDocumentAutomation(mkNotice({ document_automation: "no" as unknown as Record<string, unknown> })),
    ).toBeNull();
  });

  it("returns null when checklist is missing or not an array", () => {
    expect(
      readDocumentAutomation(
        mkNotice({ document_automation: { drafts: {} } }),
      ),
    ).toBeNull();
    expect(
      readDocumentAutomation(
        mkNotice({ document_automation: { checklist: "x" } }),
      ),
    ).toBeNull();
  });

  it("normalizes optional array fields when missing or wrong type", () => {
    const docs = readDocumentAutomation(
      mkNotice({
        document_automation: {
          checklist: [mkItem({ id: "a" })],
          // risks / missing_required / errors omitted or wrong-type
          risks: "not-an-array",
          source: "rule+llm",
        },
      }),
    );
    expect(docs).not.toBeNull();
    const result = docs as DocumentAutomationResult;
    expect(result.risks).toEqual([]);
    expect(result.missing_required).toEqual([]);
    expect(result.errors).toEqual([]);
    expect(result.drafts).toEqual({});
    expect(result.generated_at).toBe("");
    expect(result.source).toBe("rule+llm");
    expect(result.ready_for_submission).toBe(false);
  });

  it("preserves all fields when fully populated", () => {
    const fullDocs: DocumentAutomationResult = {
      checklist: [
        mkItem({ id: "bid_form", status: "generated" }),
        mkItem({ id: "biz_reg", status: "needed" }),
      ],
      drafts: { technical_compliance: { kind: "markdown", content: "x" } },
      risks: ["마감 임박"],
      generated_at: "2026-06-03T08:00:00+00:00",
      source: "rule+llm",
      ready_for_submission: true,
      missing_required: [],
      errors: [{ stage: "document_llm", detail: "n/a" }],
    };
    const docs = readDocumentAutomation(
      mkNotice({ document_automation: fullDocs }),
    );
    expect(docs).toEqual(fullDocs);
  });
});

describe("documentSummaryText", () => {
  it("reports 0/N when all required items are still needed", () => {
    const text = documentSummaryText({
      checklist: [
        mkItem({ id: "a", required: true, status: "needed" }),
        mkItem({ id: "b", required: true, status: "needed" }),
        mkItem({ id: "c", required: true, status: "needed" }),
      ],
      drafts: {},
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    });
    expect(text).toBe("서류: 0/3 준비 · 누락 3 · 초안 0");
  });

  it("counts ready and generated as prepared, draft count = drafts keys", () => {
    const text = documentSummaryText({
      checklist: [
        mkItem({ id: "a", required: true, status: "ready" }),
        mkItem({ id: "b", required: true, status: "generated" }),
        mkItem({ id: "c", required: true, status: "needed" }),
        mkItem({ id: "d", required: false, status: "not_applicable" }),
      ],
      drafts: { bid_form: {}, technical_compliance: {} },
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [mkItem({ id: "c", required: true, status: "needed" })],
      errors: [],
    });
    // required total = 3 (a, b, c); ready = 2 (a, b); missing_required.length = 1
    expect(text).toBe("서류: 2/3 준비 · 누락 1 · 초안 2");
  });

  it("falls back to (total - ready) when missing_required is empty", () => {
    const text = documentSummaryText({
      checklist: [
        mkItem({ id: "a", required: true, status: "ready" }),
        mkItem({ id: "b", required: true, status: "needed" }),
      ],
      drafts: {},
      risks: [],
      generated_at: "",
      source: "rule",
      ready_for_submission: false,
      missing_required: [],
      errors: [],
    });
    expect(text).toBe("서류: 1/2 준비 · 누락 1 · 초안 0");
  });
});

describe("nextNoticeAction", () => {
  const readyDocs: DocumentAutomationResult = {
    checklist: [
      mkItem({ id: "bid_form", status: "generated" }),
      mkItem({ id: "business_registration", status: "ready" }),
      mkItem({ id: "technical_compliance", status: "generated" }),
    ],
    drafts: {
      technical_compliance: { kind: "markdown", content: "x" },
    },
    risks: [],
    generated_at: "",
    source: "rule",
    ready_for_submission: false,
    missing_required: [],
    errors: [],
    uploads: [],
    exports: [],
  };

  it("walks the bid operations workflow in order", () => {
    expect(nextNoticeAction(mkNotice({}, { status: "collected" }))).toBe("공고 분석 필요");

    expect(nextNoticeAction(mkNotice({}, { status: "analyzed" }))).toBe("그레이딩 필요");

    expect(
      nextNoticeAction(
        mkNotice({}, { status: "analyzed", graded_at: "2026-06-22T00:00:00+09:00" }),
      ),
    ).toBe("서류 분석 필요");

    expect(
      nextNoticeAction(
        mkNotice(
          {
            document_automation: {
              ...readyDocs,
              checklist: [
                mkItem({ id: "bid_form", status: "needed" }),
                mkItem({ id: "business_registration", status: "ready" }),
              ],
            },
          },
          { graded_at: "2026-06-22T00:00:00+09:00" },
        ),
      ),
    ).toBe("필수 서류 준비 필요 (1건)");

    expect(
      nextNoticeAction(
        mkNotice(
          { document_automation: readyDocs },
          { graded_at: "2026-06-22T00:00:00+09:00", spec_item_count: 0 },
        ),
      ),
    ).toBe("규격 추출 필요");

    expect(
      nextNoticeAction(
        mkNotice(
          { document_automation: readyDocs },
          { graded_at: "2026-06-22T00:00:00+09:00", spec_item_count: 3 },
        ),
      ),
    ).toBe("규격대응표 작성 필요");

    expect(
      nextNoticeAction(
        mkNotice(
          {
            document_automation: {
              ...readyDocs,
              exports: [
                {
                  kind: "excel",
                  draft_id: "technical_compliance",
                  output_path: "x.xlsx",
                  mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  generated_at: "2026-06-22T00:00:00+09:00",
                },
              ],
            },
          },
          { graded_at: "2026-06-22T00:00:00+09:00", spec_item_count: 3 },
        ),
      ),
    ).toBe("제안서 초안 생성 필요");
  });

  it("returns final-review action once proposal draft exists and documents are ready", () => {
    expect(
      nextNoticeAction(
        mkNotice(
          {
            document_automation: {
              ...readyDocs,
              ready_for_submission: true,
              drafts: {
                ...readyDocs.drafts,
                proposal: { kind: "hwp_proposal", values: {} },
              },
              exports: [
                {
                  kind: "excel",
                  draft_id: "technical_compliance",
                  output_path: "x.xlsx",
                  mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  generated_at: "2026-06-22T00:00:00+09:00",
                },
              ],
            },
          },
          { graded_at: "2026-06-22T00:00:00+09:00", spec_item_count: 3 },
        ),
      ),
    ).toBe("최종 검토 가능");
  });
});

describe("bidWorkflowSteps", () => {
  it("marks the current step according to review-document-spec-compliance-proposal order", () => {
    const notice = mkNotice(
      {
        document_automation: {
          checklist: [
            mkItem({ id: "bid_form", status: "generated" }),
            mkItem({ id: "business_registration", status: "ready" }),
            mkItem({ id: "technical_compliance", status: "generated" }),
          ],
          drafts: { technical_compliance: { kind: "markdown", content: "x" } },
          risks: [],
          generated_at: "",
          source: "rule",
          ready_for_submission: false,
          missing_required: [],
          errors: [],
          exports: [],
        },
      },
      {
        status: "documents_analyzed",
        graded_at: "2026-06-22T00:00:00+09:00",
        spec_item_count: 0,
      },
    );

    expect(bidWorkflowSteps(notice).map((step) => [step.id, step.state])).toEqual([
      ["review", "done"],
      ["documents", "done"],
      ["spec", "current"],
      ["compliance", "pending"],
      ["proposal", "pending"],
    ]);
  });

  it("marks proposal done when proposal draft exists after compliance export", () => {
    const notice = mkNotice(
      {
        document_automation: {
          checklist: [mkItem({ id: "technical_compliance", status: "generated" })],
          drafts: {
            technical_compliance: { kind: "markdown", content: "x" },
            proposal: { kind: "hwp_proposal", values: {} },
          },
          risks: [],
          generated_at: "",
          source: "rule",
          ready_for_submission: true,
          missing_required: [],
          errors: [],
          exports: [
            {
              kind: "excel",
              draft_id: "technical_compliance",
              output_path: "x.xlsx",
              mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              generated_at: "2026-06-22T00:00:00+09:00",
            },
          ],
        },
      },
      {
        status: "hwp_composed",
        graded_at: "2026-06-22T00:00:00+09:00",
        spec_item_count: 5,
      },
    );

    expect(bidWorkflowSteps(notice).map((step) => step.state)).toEqual([
      "done",
      "done",
      "done",
      "done",
      "done",
    ]);
  });
});
