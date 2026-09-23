# Decision Layer — Day 1

This opt-in module turns a validated `company.yaml` policy and one public bid notice into four
typed decisions, then routes the result by the weakest confidence. The workspace supports an
opt-in manual classification job. It does not change collection, grading, participation,
approval, notifications, or bid submission.

## Structure

```text
company.yaml
  -> CompanyPolicy (Pydantic)
  -> DecisionEngine
       -> JevEngine (optional typesafe-sdk)
       -> future OpenAI / Claude / Local adapters
  -> EngineDecision (Pydantic)
  -> confidence router
  -> notice_decisions (PostgreSQL/Alembic)
```

The four Day 1 signals are `product_family`, `application`, `company_relevance`, and
`bid_priority`. `auto_process` only means that downstream non-destructive processing may
continue. It never means bid approval, legal eligibility, price approval, or submission.

## Files

```text
api/decision/
  engine.py             provider-neutral abstract interface
  engines/jev.py        isolated TypeSafe SDK adapter
  models.py             Pydantic input, policy, decision, and routing models
  policy.py             safe YAML loader
  routing.py            confidence thresholds
  service.py            orchestration and deterministic input hash
  tables.py             SQLAlchemy Core table
  storage.py            idempotent PostgreSQL/SQLite persistence
  __main__.py           one-notice CLI
alembic/versions/0018_decision_layer.py
config/company.example.yaml
examples/decision_notice.json
tests/test_decision_layer.py
```

## Install and configure

Python 3.11 is supported. The official SDK is an optional extra so the rest of autojebi and all
offline tests work without it.

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev,jev]"
Copy-Item config/company.example.yaml config/company.yaml
```

Edit only the non-secret policy in `config/company.yaml`. Put credentials in `.env`, never YAML:

```dotenv
TYPESAFE_API_KEY=...
TYPESAFE_DEFAULT_MODEL=jev-latest
```

The adapter uses the official `TypeSafeClient.system_one` API and sends all four Choice questions
in one request. It retains the selected labels, full probability maps, API confidence, and the
resolved model version. Provider or network errors are raised; they are never converted to a zero
score or an irrelevant classification. There is no automatic provider fallback.

## Run one decision

Without persistence:

```powershell
python -m api.decision --company config/company.yaml --notice examples/decision_notice.json
```

Apply the database migration before using `--save`:

```powershell
alembic upgrade head
python -m api.decision --company config/company.yaml --notice examples/decision_notice.json --save
```

`--save` requires the notice number to exist in `bid_pipeline`; the foreign key intentionally
prevents orphan decisions. An identical notice input, policy version, engine, and model is stored
once. Decision history is not written into `bid_pipeline.status` or v2 participation state.

## Routing

The router uses the minimum of the four confidence values:

| Minimum confidence | Route |
|---|---|
| `>= 0.90` | `auto_process` |
| `>= 0.70` | `llm_verify` |
| `< 0.70` | `human_review` |

Thresholds live in `company.yaml` and are validated so the auto threshold cannot be lower than
the verification threshold. Before production, calibrate these values with labeled historical
notices; do not assume a provider confidence is equivalent to business accuracy.

## Add OpenAI, Claude, or a local engine

Implement `DecisionEngine.decide()` and return the same `EngineDecision`. Keep provider parsing,
credentials, and retries inside the adapter. In this repository, an OpenAI or Claude adapter must
reuse `api.workspace.providers` rather than instantiate a new paid client or silently fall back.
The service, router, database table, and tests remain unchanged.

## Verify

```powershell
pytest tests/test_decision_layer.py tests/test_alembic_metadata.py tests/test_ontology_migration.py -q
ruff check api/decision tests/test_decision_layer.py alembic/versions/0018_decision_layer.py
```

Live Jev calls are intentionally excluded from pytest. The adapter test injects a fake System One
client and checks the exact request/response mapping without credentials, cost, or network access.

## Manual workspace integration

Apply migration `0018_decision_layer` to the validation DB, then configure the API and split
workers with `WORKSPACE_JEV_ENABLED=true` and `WORKSPACE_JEV_POLICY_PATH=config/company.yaml`.
The default is disabled. For synthetic rehearsals use `config/company.example.yaml` explicitly.
After changing process settings, restart both the API and workers.

`GET /v2/notices/{notice_no}/classification` returns availability, policy/model identity,
`request_hash`, `current_job_id`, and job history. Submit `kind=jev`, `input_version`,
`idempotency_key`, and that `classification_hash` to the existing jobs endpoint. The server
locks the workspace and freezes the full policy, model, and source text. Only `notice_source`
text is sent with the configured policy; company evidence/reference documents are excluded.

The external worker issues one SDK request, with retries disabled. Identical requests reuse
the original job across review-only input versions, including failed/uncertain records.
Changing the model does not reset the maximum two requests per notice/content/policy.
Automatic fallback and generic recovery/re-generation are disabled for JEV. An unchanged
failed request currently requires operator investigation; there is no retry override endpoint.

At completion the claim token, input version, source identity and full current policy/model
are checked before the immutable decision row and job success are committed together.
Historical results remain available after original text or policy changes. They cannot be
applied as requirements or used to approve participation or submission readiness.

Offline integration: `pytest tests/test_workspace_jev.py -q`.
Explicit live rehearsal from `frontend`: set `E2E_BASE_URL=http://127.0.0.1:3002`,
`E2E_API_BASE=http://127.0.0.1:8002`, `E2E_JEV_LIVE=true`, then run
`npx playwright test jev-live.spec.ts --project=workspace-v2 --retries=0`.
This creates a fresh TEST ONLY notice and sends one fictional HIL source to JEV.
See [validation record](../../docs/jev-workspace-integration-2026-09-21.md).
