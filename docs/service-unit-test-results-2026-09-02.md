# autoJEBI Service Unit Test Results - 2026-09-02

## Summary

서비스별 단위테스트를 백엔드와 프론트 UI 묶음으로 나눠 실행했다.
모든 서비스 묶음은 통과했다.

- Backend service groups: passed
- Frontend service groups: passed
- Frontend typecheck: passed
- Excluded from unit-test pass: live external integration tests such as `tests/test_qualification_live.py`

## Environment

- Workspace: `C:\Users\junpr\autojebi`
- Backend test runner: `pytest`
- Frontend test runner: `vitest`
- Frontend typecheck: `tsc --noEmit --incremental false`
- Date: 2026-09-02

## Backend Results

| Service group | Scope | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 운영 기반/API 공통 | DB migration metadata, auth, CORS, health, status routing, E2E cleanup | `pytest -q tests/test_alembic_metadata.py tests/test_migration_revision_ids.py tests/test_auth.py tests/test_cors.py tests/test_healthz.py tests/test_status.py tests/test_routing.py tests/test_e2e_cleanup_endpoint.py` | Passed | No failure |
| 공고 수집/검색 | Collector pipeline, G2B search, saved notice search, summary, G2B client, attachments, mail extraction | `pytest -q tests/test_collector_pipeline.py tests/test_notices_g2b_search.py tests/test_notices_search.py tests/test_notices_summary.py tests/test_g2b_client.py tests/test_g2b_attachments_fetch.py tests/test_attachments.py tests/test_mail_extractor.py tests/test_extractor.py` | Passed | No failure |
| 분석/분류 | Claude analyzer, JSON parsing fallback, schema error handling, fit score, category mapping | `pytest -q tests/test_claude_analyzer.py tests/test_claude_json_parsing.py tests/test_notice_analyze_schema_errors.py tests/test_fit_score.py tests/test_category_mapping.py` | Passed | No failure |
| 그레이딩/SKU/온톨로지 | Grade endpoint, grading runner/scorer/summarizer, qualifications, qual cache, ontology, Qdrant store, SKU matcher, scheduler | `pytest -q tests/test_grade_endpoint.py tests/test_grading_runner.py tests/test_grading_scorer.py tests/test_grading_summarizer.py tests/test_fetch_qualifications.py tests/test_qual_cache.py tests/test_ontology_migration.py tests/test_ontology_routes.py tests/test_ontology_seed.py tests/test_qdrant_store.py tests/test_sku_matcher.py tests/test_auto_grade_scheduler.py` | Passed | Qdrant client/server version warning only |
| 문서 자동화/HWP | Document automation, required docs, uploads, exports, HWP health/client, HWP field mapping, spec items | `pytest -q tests/test_document_automation.py tests/test_required_documents.py tests/test_uploads_service.py tests/test_documents_uploads_endpoint.py tests/test_documents_exports_endpoint.py tests/test_exporters.py tests/test_documents_hwp_health.py tests/test_hwp_agent_client.py tests/test_hwp_field_mapping.py tests/test_spec_items.py` | Passed | No failure |
| 제안서/알림 | Proposal Agent, Teams/notification flow, Slack notifier | `pytest -q tests/test_proposal_agent.py tests/test_notifications.py tests/test_slack_notifier.py` | Passed | No failure |

## Frontend Results

| Service group | Scope | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 공고 검색/등록 UI | API client, server actions, G2B search dialog, manual upsert, notice filter | `npm test -- --run src/lib/__tests__/api.test.ts src/lib/__tests__/actions.test.ts src/components/__tests__/G2BSearchDialog.test.tsx src/components/__tests__/UpsertNoticeForm.test.tsx src/components/__tests__/NoticeFilterBar.test.tsx` | Passed: 5 files, 29 tests | Vite CJS deprecation warning only |
| 공고 상세/워크플로우 UI | Action bar, workflow rail, status/score/category badges, metric cards, toast, modal | `npm test -- --run src/components/__tests__/NoticeActionsBar.test.tsx src/components/__tests__/BidWorkflowRail.test.tsx src/components/__tests__/StatusBadge.test.tsx src/components/__tests__/ScoreBadge.test.tsx src/components/__tests__/CategoryBadge.test.tsx src/components/__tests__/MetricCard.test.tsx src/components/__tests__/Toast.test.tsx src/components/__tests__/Modal.test.tsx` | Passed: 8 files, 47 tests | Vite CJS deprecation warning only |
| 문서/HWP/제안서 UI | Document automation helpers, document preparation panel, HWP compose, proposal compose, autofill dialog | `npm test -- --run src/lib/__tests__/documentAutomation.test.ts src/components/__tests__/DocumentPreparationPanel.test.tsx src/components/__tests__/HwpComposeDialog.test.tsx src/components/__tests__/ProposalComposeDialog.test.tsx src/components/__tests__/AutofillDialog.test.tsx` | Passed: 5 files, 34 tests | Vite CJS deprecation warning only |

## Typecheck

| Scope | Command | Result |
| --- | --- | --- |
| Frontend TypeScript | `npm run typecheck` | Passed |

## Warnings

- Qdrant warning: `qdrant_client` reported a client/server version mismatch during the grading/SKU test group. This did not fail tests.
- Vitest warning: Vite CJS Node API deprecation warning appeared during frontend tests. This did not fail tests.
- Frontend tests required normal process execution permission on Windows because the sandbox blocked `esbuild` process spawn with `EPERM`.

## Not Included In Unit-Test Pass

- `tests/test_qualification_live.py` is treated as a live external integration test and was not included in the service unit-test pass.
- Browser-driven E2E and real HWP Worker smoke tests are separate from this unit-test document.

