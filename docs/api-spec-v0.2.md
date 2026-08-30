# API 명세 v0.2 — 공고 검색부터 규격서/HWP 작성까지

이 문서는 Phase 0 기준 계약 문서다. 구현 변경이나 DB 마이그레이션을 전제하지 않고, 프론트엔드·백엔드·milim-hwp-agent가 같은 route와 데이터 경계를 보도록 현재 구현과 후속 설계를 분리한다.

## 1. 식별자 규칙

- 공고의 공개 path 식별자는 항상 `notice_no`다.
- 공고 종속 route는 `/notices/{notice_no}/...` 형식만 사용한다.
- `notice_no`에 대한 legacy alias는 없다.
- `item_id`, `upload_id`, `kind`는 하위 리소스 식별자이며 공고 식별자로 쓰지 않는다.
- 전역 리소스는 공고 path 아래에 두지 않는다. 예외 전역 route는 `/documents/common/uploads`, `/documents/hwp-agent/health`다.

## 2. 표준 Route 표

| 작업 단계 | Method | Route | 주요 입력 | 주요 출력 | 상태/Side effect |
|---|---:|---|---|---|---|
| 공고 검색 | POST | `/notices/search` | 검색어, 날짜, source, paging | 검색 결과, `already_exists` | DB write 없음 |
| 공고 저장 | POST | `/notices/upsert` | `notice_no`, title, raw, 정규 컬럼 | `NoticeRecord` | 신규는 `collected`, 기존 분석/상태 보존 |
| 공고 분석 | POST | `/notices/{notice_no}/analyze` | 없음 또는 분석 옵션 | category, fit_score, assignee, analysis | `collected -> analyzed` |
| 3축 그레이딩 | POST | `/notices/{notice_no}/grade` | `{ alert?: boolean }` | spec/qual/price/total, SKU, reason | 점수 갱신, status는 유지 |
| 알림 | POST | `/notices/{notice_no}/notify` | `{ dry_run?: boolean }` | `{ status, delivered }` | 처리 상태에서 final 3종으로 전이 |
| HWP 입찰양식 autofill | POST | `/notices/{notice_no}/autofill-form` | template/output/values | replaced, missing, remaining_placeholders | `form_filled` 전이, bid form draft 저장 |
| G2B 첨부 가져오기 | POST | `/notices/{notice_no}/attachments/fetch` | 없음 | `job_id`, job status, 파일별 결과, 다운로드/분석 결과 목록 | `attachments_fetched` 전이, uploads/errors/job 저장 |
| 서류 분석 | POST | `/notices/{notice_no}/documents/analyze` | 없음 | checklist, drafts, uploads, errors | `documents_analyzed` 전이, `analysis.document_automation` 갱신 |
| 체크리스트 수정 | PATCH | `/notices/{notice_no}/documents/checklist/{item_id}` | status, owner, note | 갱신된 document automation | 수동 수정값 보존 |
| 제출 전 검증 | POST | `/notices/{notice_no}/documents/validate` | 없음 | ready 여부, missing/blocked | status 변경 없음 |
| 사용자 업로드 | POST | `/notices/{notice_no}/documents/uploads` | multipart file, optional item_id | upload metadata, automation | 파일 저장, 분석/자동분류, checklist ready 승격 가능 |
| 업로드 목록 | GET | `/notices/{notice_no}/documents/uploads` | 없음 | uploads[] | status 변경 없음 |
| 업로드 다운로드 | GET | `/notices/{notice_no}/documents/uploads/{upload_id}/download` | 없음 | file stream | 파일 누락 시 오류 |
| 업로드 삭제 | DELETE | `/notices/{notice_no}/documents/uploads/{upload_id}` | 없음 | deleted id | metadata와 디스크 파일 삭제 |
| 공통 서류 등록 | POST | `/documents/common/uploads` | multipart file, label/item 힌트 | common upload metadata | 전역 공통 서류함에 저장 |
| 공통 서류 목록 | GET | `/documents/common/uploads` | 없음 | common uploads[] | status 변경 없음 |
| 공통 서류 가져오기 | POST | `/notices/{notice_no}/documents/import-common/{upload_id}` | 없음 | upload metadata, automation | 현재 공고 uploads[]에 `source_ref=common_library` 참조 추가 |
| Excel/HWP export 생성 | POST | `/notices/{notice_no}/documents/exports/{kind}` | `kind=excel\|hwp`, optional `version` | `ExportRecord` | `notice_exports` + `exports[]`에 technical_compliance export 저장 |
| export_id 다운로드 | GET | `/notices/{notice_no}/documents/exports/by-id/{export_id}/download` | export_id | file stream | active export row 기준, 미존재 404, 파일 누락 410 |
| 최신 kind 다운로드 | GET | `/notices/{notice_no}/documents/exports/{kind}/download` | kind | file stream | 최신 active export alias, JSON fallback 유지 |
| 규격 항목 추출 | POST | `/notices/{notice_no}/spec-items/extract` | 없음 | extracted/upserted items | `spec_extracted` 전이, 근거/source_text 포함 `notice_spec_items` upsert |
| 규격 항목 목록 | GET | `/notices/{notice_no}/spec-items` | 없음 | items sorted by `sort_order` | status 변경 없음 |
| 규격 항목 수정 | PATCH | `/notices/{notice_no}/spec-items/{item_id}` | proposed_value, status, evidence, note | 갱신된 item | reviewed/matched 수동값은 재추출보다 우선 |
| 규격대응표 HWP 작성 | POST | `/notices/{notice_no}/documents/hwp-compose` | template/output/values_override | export, remaining_placeholders, errors | `hwp_composed`/`form_filled` 전이, export/error 저장 |
| 제안서 HWP 작성 | POST | `/notices/{notice_no}/documents/proposal-compose` | template_path, values_override, visible | export, proposal, remaining_placeholders, errors | 필드 매핑 기반 `/document/put-fields`, `proposal_hwp` export 저장 가능 |
| HWP 템플릿/필드 조회 | GET | `/documents/hwp-templates` | 없음 | active templates + mappings | seed/API 관리용 |
| HWP 템플릿 upsert | POST | `/documents/hwp-templates` | template_key, kind, name, template_path | template + mappings | 관리자용 생성/갱신 |
| HWP 템플릿 수정 | PATCH | `/documents/hwp-templates/{template_id}` | kind/name/path/version/active | template + mappings | `active=false`로 soft-disable |
| HWP 필드 매핑 upsert | POST | `/documents/hwp-templates/{template_id}/mappings` | field, context_path, required, transform | template + mappings | `(template_id, hwp_field_name)` 기준 갱신 |
| HWP 필드 매핑 수정 | PATCH | `/documents/hwp-templates/{template_id}/mappings/{mapping_id}` | mapping fields, active | template + mappings | `active=false`로 soft-disable |
| HWP context 미리보기 | POST | `/notices/{notice_no}/documents/hwp-context` | template_key, values_override | context, input_values, required_missing | 생성 전 검토 |
| HWP PutFieldText 생성 | POST | `/notices/{notice_no}/documents/hwp-put-fields` | template_key, output_path, values_override, visible | export, job, required_missing, remaining_placeholders | mapping 기반 HWP 생성 |
| HWP 생성 검토 | POST | `/notices/{notice_no}/documents/hwp-jobs/{job_id}/review` | review_status, note, reviewer | job | 사람 검토 상태 저장 |
| HWP agent health | GET | `/documents/hwp-agent/health` | 없음 | ok, base_url, detail | 전역 readiness 확인 |
| Proposal 문서 원장 등록 | POST | `/proposals/documents` | document metadata + chunks | document | 사내 제안서/보고서/chunk 원장 |
| Proposal 실적 등록 | POST | `/proposals/performances` | performance metadata | performance | 정확한 실적 수치 원장 |
| Proposal 요구사항 분석 | POST | `/proposals/analyze/{notice_no}` | 없음 | requirements | 공고 기반 제안 요구사항 구조화 |
| Proposal Evidence 검색 | POST | `/proposals/{notice_no}/retrieve` | 없음 | evidences | 문서 chunk + 실적 DB Top evidence 저장 |
| Proposal 섹션 생성 | POST | `/proposals/{notice_no}/generate` | 없음 | sections | Evidence ID가 연결된 초안 문장 생성 |
| Proposal 사실검증 | POST | `/proposals/{notice_no}/verify` | 없음 | sections + status | Evidence 참조와 검증필요 문구 검사 |
| Proposal coverage | GET | `/proposals/{notice_no}/coverage` | 없음 | readiness_score, items | 요구사항별 자료 확보 현황 |
| E2E cleanup | POST | `/notices/e2e/cleanup` | prefix/options | 삭제 결과 | dev/test 전용, `E2E-*` 범위만 |

## 3. 상태머신 표

### 공고 상태

공고 상태는 `bid_pipeline.status` 하나로 관리한다. 서류 상태와 규격 항목 상태는 별도 enum이며 공고 상태 전이를 직접 대체하지 않는다.

| 상태 | 의미 | 허용 다음 상태 |
|---|---|---|
| `collected` | 검색/메일/수동 저장으로 수집됨 | `analyzed` |
| `analyzed` | Claude 분석 완료, 서류/그레이딩/HWP 준비 가능 | 후속 처리 상태 또는 final |
| `attachments_fetched` | G2B 첨부 다운로드/분석 시도 완료 | 후속 처리 상태 또는 final |
| `documents_analyzed` | 필요 서류 체크리스트/초안 생성 완료 | 후속 처리 상태 또는 final |
| `spec_extracted` | 규격 항목 DB 추출 완료 | 후속 처리 상태 또는 final |
| `hwp_composed` | HWP/제안서 생성 시도 완료 | `form_filled` 또는 final |
| `form_filled` | HWP 입찰양식 autofill 또는 서류 생성 단계 완료 | final |
| `notified` | 고적합 공고 알림 완료 | final |
| `digest_queued` | 중간 적합도 공고 digest 대기 | final |
| `archived_low` | 낮은 적합도 공고 보관 | final |

자동 알림 분기 기준은 `fit_score >= 70`이면 `notified`, `40 <= fit_score < 70`이면 `digest_queued`, 그 외는 `archived_low`다. final 상태에서는 추가 전이를 허용하지 않는다.

### 서류 체크리스트 상태

| 상태 | 의미 |
|---|---|
| `needed` | 필요한 서류이나 아직 준비되지 않음 |
| `ready` | 업로드/공통 서류/첨부 분석으로 제출 준비됨 |
| `generated` | 시스템이 draft/export를 생성함 |
| `blocked` | 외부 발급, 누락값, 오류 등으로 막힘 |
| `not_applicable` | 해당 공고에는 적용하지 않음 |

### 규격 항목 상태

| 상태 | 의미 |
|---|---|
| `candidate` | 자동 추출 후보, 담당자 검토 전 |
| `reviewed` | 담당자가 요구값/제안값을 확인함 |
| `matched` | 제안 사양이 요구 사양에 대응됨 |
| `gap` | 요구 사양과 제안 사이 차이 또는 리스크 있음 |
| `ignored` | HWP/제안서 본문에서 제외할 항목 |

HWP 작성과 제안서 본문은 `candidate`, `reviewed`, `matched`를 우선 사용하고, `gap`과 `ignored`는 리스크/확인사항으로 분리한다.

`confidence < 0.75` 항목은 `review_priority="high"`로 표시한다. 규격 항목은 `source_text`, `source_file_name`, `source_page`, `evidence`를 함께 저장해 담당자가 원문 근거를 확인할 수 있게 한다.

### 첨부 fetch job 상태

`POST /notices/{notice_no}/attachments/fetch`는 동기 처리하지만 매 호출마다 `attachment_fetch_jobs`와 `attachment_fetch_files`에 추적 기록을 남긴다.

| 상태 | 의미 |
|---|---|
| `completed` | 모든 첨부가 성공 또는 중복 skip으로 처리됨 |
| `completed_with_errors` | 하나 이상의 파일 다운로드/분석 실패 또는 텍스트 추출 오류 있음 |

파일별 상태는 `pending`, `success`, `failed`, `skipped` 중 하나다.

## 4. 오류 응답과 notice_errors

### 현행 저장소

Phase 1 현재 구현은 `notice_errors`를 우선 저장소로 사용하고, 프론트 호환을 위해 `analysis.document_automation.errors[]`와 개별 API 응답의 `errors[]`에도 mirror한다. 외부 의존성 실패는 가능한 경우 전체 흐름을 중단하지 않고 파일/단계 단위 오류로 누적한다.

권장 오류 항목 shape:

```json
{
  "stage": "attachments.fetch",
  "severity": "warning",
  "source": "g2b",
  "file_name": "spec.pdf",
  "detail": "텍스트 추출 실패",
  "raw": {}
}
```

### HTTP 오류 규칙

| 코드 | 기준 |
|---:|---|
| 400 | 지원하지 않는 `kind`, 잘못된 작업 옵션 |
| 404 | 공고/하위 리소스 없음, export 미생성 |
| 409 | 선행 단계 필요, 상태 충돌, 규격 항목 없음 |
| 410 | metadata는 있으나 디스크 파일 누락 |
| 413 | 업로드 파일 크기 제한 초과 |
| 415 | 지원하지 않는 파일 형식 |
| 422 | FastAPI/Pydantic request validation 실패 |
| 502 | 외부 의존성 호출 실패를 즉시 실패로 반환해야 하는 경우 |

제안서/HWP 작성에서 agent가 실패했더라도 draft 저장이 가능하면 `errors[]`에 사유를 기록하고 export는 파일 생성이 확인된 경우에만 추가한다.

### 정규 테이블: `notice_errors`

| 필드 | 의미 |
|---|---|
| `id` | 오류 row 식별자 |
| `notice_no` | 공고 번호 |
| `stage` | `search`, `analyze`, `attachments.fetch`, `documents.upload`, `hwp.compose` 등 |
| `severity` | `info`, `warning`, `error` |
| `source` | `g2b`, `claude`, `hwp_agent`, `upload`, `exporter`, `system` |
| `file_name` | 파일 단위 오류일 때 원본명 |
| `detail` | 사용자에게 보여줄 요약 |
| `raw` | 원본 오류/응답 JSON |
| `resolved_at` | 처리 완료 시각 |
| `created_at` | 생성 시각 |

첨부 다운로드/분석 실패는 파일 단위로 `stage`, `file_name`, `source`, `detail`, `raw`를 기록한다. Claude tool-use schema 검증 실패는 `stage="claude.schema"`로 기록한다.

## 5. Export 구조와 notice_exports

### 현행 저장소

현재 export metadata는 `notice_exports`를 우선 저장소로 사용하고, 프론트 호환을 위해 `analysis.document_automation.exports[]`에도 mirror한다. Pydantic `ExportRecord` 기준 필드는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `id` | `notice_exports.id`; 없으면 legacy JSON mirror |
| `kind` | `excel`, `hwp`, `bid_form_hwp`, `proposal_hwp` 중 하나 |
| `draft_id` | `technical_compliance`, `proposal` 등 생성 기준 draft |
| `output_path` | 서버 로컬 파일 경로 |
| `mime` | 다운로드 MIME type |
| `generated_at` | 생성 시각 |
| `notes` | 생성/부분 성공/오류 보조 설명 |
| `version` | `compliance_excel_v1`, `compliance_excel_v2`, `proposal_hwp_v1` 등 산출물 버전 |
| `template_version` | HWP agent/template 계약 또는 Excel layout 버전 |
| `validation_status` | `passed`, `warning`, `failed` |
| `validation_errors` | 사전 검증/placeholder/검토 경고 목록 |
| `file_size`, `sha256` | 파일 검증용 메타데이터 |

`POST /notices/{notice_no}/documents/exports/{kind}`는 `excel`과 `hwp`만 생성한다. Excel 기본값은 `version=compliance_excel_v2`이며 `compliance_excel_v1`은 기존 단일 시트 호환 포맷이다. `bid_form_hwp`와 `proposal_hwp`는 필드 매핑 기반 `POST /notices/{notice_no}/documents/hwp-put-fields` 또는 `proposal-compose`가 생성한다.

다운로드 API는 export_id 기반 경로를 우선 사용한다. 기존 kind 기반 다운로드는 최신 active export alias로 남겨 프론트/문서 호환을 유지한다. metadata가 없으면 404, metadata는 있으나 파일이 없으면 410을 반환한다.

HWP/제안서 생성 전 `validate_pre_compose()`가 `규격 항목 없음`, 생성 대상 외 필수 서류 누락, 명시된 필수 작성값 누락을 409로 차단한다. 낮은 confidence, `candidate`, `review_priority=high` 규격 항목은 차단하지 않고 `validation_errors` warning으로 남긴다.

### 정규 테이블: `notice_exports`

| 필드 | 의미 |
|---|---|
| `id` | export row 식별자 |
| `notice_no` | 공고 번호 |
| `kind` | `excel`, `hwp`, `bid_form_hwp`, `proposal_hwp` |
| `draft_id` | export 입력 draft 식별자 |
| `output_path` | 파일 저장 경로 |
| `mime` | 다운로드 MIME type |
| `notes` | 보조 설명 |
| `version` | 산출물 버전 |
| `template_version` | 템플릿/agent 계약 버전 |
| `validation_status` | `passed`, `warning`, `failed` |
| `validation_errors` | 검증 오류/경고 JSON |
| `file_size` | 생성 파일 바이트 크기 |
| `sha256` | 생성 파일 해시 |
| `created_at` | 생성 시각 |
| `created_by` | 사용자/시스템 주체 |
| `deleted_at` | soft delete 시각 |

## 6. 범위 밖

- 실제 G2B 투찰 클릭, 금액 입력, 제출 자동화는 API 명세 범위에도 포함하지 않는다.
- `notice_errors`, `notice_exports`는 정규 저장소이며 기존 JSON 배열은 응답 호환 mirror로 유지한다.
