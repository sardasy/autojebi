# 사양 검증·하이브리드 검색 구현 및 검증

## 상태와 적용 범위

이번 변경은 autojebi v2의 HILS·시뮬레이션 검토/작성 보조 기능이다. 가격 산정, 자동 참가 결정, 투찰, 추가 유료 LLM 호출을 추가하지 않았다.

`SPEC_SEARCH_ENABLED=true`와 `SPEC_SEARCH_ENV=validation`을 모두 지정해야 새 분석 스키마·사양 교정·색인을 활성화한다. 기본값은 비활성이다. 기존 실행 중인 3000/8001 및 HWP Worker를 재시작하거나 변경하지 않았다. 현재 8002 서버에도 이 변경을 재배포하지 않았다.

검색용 PostgreSQL/Neo4j/Qdrant는 `infra/docker-compose.spec-validation.yml`의 별도 Compose 프로젝트다. API/프론트 검증 주소는 계속 8002/3002이며, 저장소 검증 포트는 각각 localhost 15433/17687/16333이다. 운영 DB 대신 새 `spec_validation` DB에 마이그레이션했다.

## 데이터와 판정

- 원문 파일·본문 해시와 인용 시작/끝 위치, 원문 표현, 대상, 속성, 연산자, 값/범위, 단위, 조건, 필수 여부를 보존한다.
- 숫자는 문자열로 받아 Decimal로 비교한다. 명시되지 않은 허용오차는 0이며, 측정 불확도 구간이 경계를 걸치면 미확인이다. 999.97μs는 1ms 이하를 충족하지만 1000.01μs는 충족하지 않는다.
- `tolerance`(요구 허용오차)와 `uncertainty`(측정 불확도)는 별개다. `허용오차 ±`처럼 명시된 표현만 허용 범위로 사용하며, 요구사항에 측정 불확도만 있는 경우 자동 판정하지 않는다. 현재 지원하지 않는 단위·기호 표현은 원문을 보존하고 확인 필요로 남긴다.
- 속성과 단위 차원을 함께 검사한다. 시간 간격/지연, 유효전력/피상전력은 같은 값처럼 취급하지 않는다. 모델·프로토콜·버전은 구두점을 유지한다.
- 결정적 파서와 LLM 후보를 대조한다. 지원하지 않는 표현, 조건부 문장, 모호한 부정, 쉼표 숫자의 부분 인식, 잘린 문장은 자동 확정하지 않는다.
- 단순 이중 부정, 명시적인 열린/닫힌 범위, ± 불확도는 원문 표현과 일치할 때 처리한다. SHACL은 구조 검증이며 사실 승인으로 사용하지 않는다.
- 표에는 셀·병합 범위·헤더 경로·원문 좌표를 별도로 보존한다. PDF/OCR/HWP의 불확실한 구조는 확인 필요로 남기며 빈 셀을 자동 채우지 않는다. 확인된 수동 변환 본문 등록은 기존 감사/버전 경로를 사용한다.
- 셀 값과 본문 위치가 유일하고 구조가 확인된 경우에만 헤더·행 이름·단위를 검색 문맥에 추가한다. 검색 문맥은 원문 인용/오프셋과 분리하며, 이 문맥으로 숫자 관측값을 새로 만들어내지 않는다. 중복 셀·반복 본문·불명확한 헤더는 연결하지 않는다.
- 저장된 회사 참고자료는 증빙으로 승격하지 않는다. 검색한 근거를 선택한 다음 사용자가 발췌문 삽입·초안 저장을 각각 실행한다. 검색/저장이 사람 승인이나 참가 결정을 변경하지 않는다.
- 유효성 메타데이터가 없는 과거 확인 문서는 참고 그룹에만 표시한다. 새 사양 준비도 집계도 같은 유효성 기준을 사용한다. 회사 자료는 회사 주체 일치까지 확인한다.

## 검색·세대 관리

PostgreSQL `simple` 전문 검색 + 정확 식별자 JSONB 색인, Neo4j 관계 검색, BGE-M3 dense1024/cosine 검색을 결합한다. Neo4j에는 공고→요구사항→속성/제품 및 원문→근거 관계를 세대별로 저장한다. 모델은 명시적인 40자리 리비전과 로컬 snapshot만 허용하며 원격 코드 실행 및 조회 중 다운로드를 금지한다. 실제 검증 리비전은 `5617a9f61b028005a4858fdac845db406aefb181`이다.

세 축의 최대 100건을 동일 근거 구간 ID로 결합한다. RRF는 `sum(1/(60+rank))`, 가중치는 모두 1, 동점은 ID 순이다. 확인된 증빙/참고자료/불충족 자료를 분리하고 검증 여부로 점수를 몰래 올리지 않는다. UI에 축별 순위와 수치 판정을 표시한다.

색인은 외부 실행기의 `spec_index` 작업이다. 같은 입력/모델 명세의 실패 세대는 완료한 저장소를 보존하고 실패한 저장소만 재처리한다. 결과를 이전 세대에 덮어쓰지 않는다. 자료·모델·청킹·정규화 변경은 새 세대를 만든다. 요청과 완료 모두 입력 버전·입력 해시·claim token을 확인한다.

색인 완료는 검색 공개가 아니다. 평가 보고서를 통과한 세대만 CLI로 공개하며 활성 매니페스트는 한 트랜잭션으로 바꾼다. 이전 세대는 최소 7일 보존하도록 기한을 기록하고 자동 삭제하지 않는다. 이전 보고서를 사용한 명시적 재공개로 롤백하되 현재 입력 버전·해시가 일치해야 한다. 모든 검색은 외부 조회 이후에도 현재 자료와 파일 무결성·만료 여부를 다시 확인한다.

## API

모두 기존 `/v2` 인증을 사용한다.

- `GET /v2/notices/{notice_no}/specifications`: 사양 목록, 자동 검증 진단, 입력 버전, 사람 검토 기반 종합 상태 및 `index_state`(현재/최신 세대, 상태, 입력 일치).
- `GET /v2/notices/{notice_no}/specifications/{id}`: 교정 대상과 강한 ETag.
- `PUT /v2/notices/{notice_no}/specifications/{id}`: `{version,payload,note}` + `If-Match`. 누락 428, ETag 불일치 412, 입력 버전 충돌 409. 원자적 이력 저장, 충돌 시 자동 재시도 없음.
- `POST /v2/notices/{notice_no}/spec-search`: `{requirement_id?,query,limit}`. 증빙/참고/불충족 그룹, RRF·축별 순위, 제한 검색 사유, 세대 ID.
- 기존 작업 생성 API의 `kind=spec_index`: 202로 접수하고 기존 작업 조회 API로 추적한다.
- 기존 요구사항 분석/등록/채택에는 선택적 `specification`을 추가했다. 기존 요구사항·수동 반려를 덮어쓰지 않는다.

목록/상세의 `spec_compliance`, `unresolved_spec_count`, `spec_source_complete`는 공통 집계다. 자동 수치 비교 결과를 사람의 적합 판정에 쓰지 않는다. 원문 누락·필수 사양 미확인은 준비 완료를 차단하지만 검토용 다운로드는 허용한다.

## 실행과 평가

```powershell
python -m pip install -e ".[dev,spec-search]"
python tools/spec_validation_runtime.py up
python tools/spec_validation_runtime.py model
python tools/spec_validation_runtime.py test
python -m api.specifications graph-schema
python -m api.specifications evaluate --dataset DATASET.json --results RESULTS.json --manifest-hash HASH --output REPORT.json
python -m api.specifications publish --notice NOTICE --generation GENERATION --report REPORT.json
```

검증 전용 자격 증명과 모델은 gitignore된 `data/spec-validation`에 보관한다. 도구는 운영 `.env` 비밀값을 복사하지 않는다. `graph-schema`는 검증 Neo4j 환경을 지정한 상태에서 고정된 제약만 생성하며, 데이터 검색/색인은 제약을 몰래 생성하지 않는다. `publish`는 대상 검증 DB 환경을 명시적으로 지정한 프로세스에서만 실행한다.

평가기는 개발 40건, 홀드아웃 200건(수치/인터페이스·모델/라이선스/버전 각각 50건), 문서군/원본 해시의 split 분리, 범주별 Recall@5, 원시/최종 순위, 문서군 bootstrap 95% 구간을 검사한다. 실제 검토자와 문서 해시가 필요하며 합성 코퍼스는 성능 공개 게이트를 통과할 수 없다. 정답 목록에 없는 안전 평가 자료를 임의로 충족 처리해도 게이트가 닫힌다. 릴리스마다 실제 실패 사례 20건 이상을 회귀셋으로 이관하고 새 홀드아웃을 보충한다.

## 검증 기록과 남은 조건

- 최종 전체 백엔드 실행: **1622 passed / 17 skipped**, 실패/오류 0건, 74.201초 (`tmp/spec-search-pytest-release.xml`). 실연동 opt-in 등 건너뛴 항목과 아래 별도 실연동 실행을 구분한다.
- 최종 전체 프론트 단위 실행: **231 passed / 33 files**. 프론트 타입 검사 및 lint 통과.
- 실제 새 PostgreSQL: head 마이그레이션, 0016으로 되돌리기/재적용, 정확 식별자 + 전문 검색 통과.
- 실제 Neo4j: 관계 적재·재적재·관계 조회 통과.
- 실제 BGE-M3/Qdrant: 한국어 사양 로컬 임베딩, 저장, 검색 통과. 회사 실제 자료 대신 TEST 합성 문장을 사용했다.
- 실제 통합 큐/동시 수정: **통과**. 동일 ETag 동시 저장은 `[200,412]`; 외부 실행기의 `spec_index`로 3개 저장소 적재 완료; 정상/불충족 수치가 서로 다른 결과 그룹으로 반환된다. 참가 결정은 미결정 유지, 공개 매니페스트 자동 생성 없음.
- 실제 격리 저장소 시험은 총 **4 passed**이며, 데이터는 TEST 합성 문장이다. 실제 공고 품질 평가가 아니다.
- 3002 mock 브라우저: **8 passed**. 1280×800/390×844에서 교정 충돌 보존, 제한 검색/그룹, 비활성 상태, 근거 선택→발췌문 삽입→초안 저장(202)을 실제 버튼으로 확인했다. 외부 API/유료 호출은 차단했다.
- 화면 기록: `frontend/test-results/specification-mock-specifi-1a850-ate-insert-and-save-actions-workbench-mock/selection-viewport-1280x800.png`, `frontend/test-results/specification-mock-specifi-80da7-ate-insert-and-save-actions-workbench-mock/selection-viewport-390x844.png`.
- `ruff check api tests tools/spec_validation_runtime.py alembic/versions/0017_spec_search.py`: 통과. 저장소 전체 `ruff check .`는 이번 변경 밖의 기존 `tmp/` 보조 스크립트에서 17건으로 실패했다. 기존 파일을 수정하거나 검사에서 숨기지 않았다.

**출시 미완료:** 사람이 판정한 실제 공고 홀드아웃 200건과 개발 40건을 아직 확보하지 못했다. 합성 평가기 테스트를 실제 Recall@5 달성으로 보고하지 않는다. 활성 매니페스트를 공개하거나 운영 환경을 전환하지 않았다. 범용 HWP/PDF 표 의미 복원은 자동 확정 대상이 아니며 모호한 구조는 계속 확인이 필요하다.

환경 경고: 기존 Qdrant 서버 1.15.5와 설치된 클라이언트 1.18.0의 버전 차이 경고가 있다. 검증용 서버에도 동일 버전을 사용했고 실제 기본 저장/검색은 통과했지만 운영 전 버전 정렬이 필요하다. 경고를 숨기지 않았다.

## 기준 문서

구조 검사는 [W3C SHACL](https://www.w3.org/TR/shacl/), 단어 토큰화와 식별자 정확 검색 분리는 [PostgreSQL 16 파서 문서](https://www.postgresql.org/docs/16/textsearch-parsers.html), 강한 ETag/If-Match와 412 처리는 [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)을 대조했다. SHACL 통과를 사실 확인으로 해석하지 않는다.
