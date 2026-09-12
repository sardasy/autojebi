# autoJEBI Demo Runbook

## Goal

Show a live, human-in-the-loop bid workflow with real G2B search and the Windows HWP Worker.
The demo must never automate final G2B bid submission, bid amount entry, or submit clicks.

## Required Environment

- API and frontend are running from the latest commit.
- `DATABASE_URL` points to the demo database.
- `DATA_GO_KR_API_KEY` is configured for live G2B search.
- `QDRANT_URL` is reachable and SKU catalog ingest has completed.
- `HWP_AGENT_BASE_URL` points to the Windows HWP Worker.
- `HWP_AGENT_TOKEN` is configured when the worker requires it.
- `python -m api.ontology seed` has been run.
- `python -m api.hwp_fields seed` has been run.
- HWP template files exist on the worker machine and contain fields matching DB mappings.

## Demo Flow

1. Open `/admin` and confirm the demo readiness panel has no blocking failures.
2. Run `Qdrant에 인제스트` if SKU readiness needs refreshing.
3. Open `/notices?mode=g2b`, search a prepared keyword such as `변압기`, `차단기`, or `전력변환`.
4. Save one G2B result and follow `상세로 이동`.
5. On the notice detail page, run `분석`, then run `그레이드`.
6. In `서류 준비`, fetch attachments, run document analysis, and validate required documents.
7. Run HWP creation and verify the visible result: output path, job status, required missing,
   remaining placeholders, and review status.
8. Approve or reject the HWP job from the document panel.
9. Run Teams notification with dry-run enabled and confirm the saved status.

## Fallback Script

- If G2B is unavailable, use `/admin` manual upsert with a prepared notice number and continue from detail.
- If HWP Worker is unavailable, show the health warning and execute the HWP action to demonstrate the
  visible failure message and saved job/error state.
- If Qdrant is unavailable, continue with grading fallback and call out the warning in `/admin`.
