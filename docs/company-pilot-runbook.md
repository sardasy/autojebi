# 회사 증빙 실무 평가 — 측정 도구 사용법

2026-09-22 사용자 확인: 실무 담당자와 실제 증빙은 **확보 전**이다.
현재 실제 측정 결과는 없고 목표도 확정하지 않았다. 합성 테스트 수치를 실무 성과로 사용하지 않는다.

## 1. 준비한 파일

저장소 루트에서 아래 명령으로 새 폴더를 만든다. 기존 파일은 덮어쓰지 않는다.

```powershell
.venv/Scripts/python.exe -m tools.company_pilot init data/company-pilot/새-평가명
```

이번 작업에서는 `data/company-pilot/2026-09-22`에 빈 양식을 생성했다.
이 디렉터리는 실제 담당자·공고·증빙 메타데이터를 담을 수 있으므로 git에서 제외한다.
증빙 원본 자체는 기존 회사자료 보관소를 사용한다.

| 파일 | 입력할 것 |
|---|---|
| pilot.json | 담당자/주당 시간, A~E 선정표, 기준선 5건, 초안 대상 2건, 목표 |
| measurement-template.json | 실제 측정 행의 빈 양식. 복사해 baseline 또는 runs에 넣는다 |
| improved.json | 고정 프로토콜 해시, B~E에 쓸 코드/규칙 버전, 자료 준비 비용, 개선 실행 결과 |

`null`은 미측정이다. 0은 실제로 측정한 값이 0인 경우에만 쓴다.
담당자가 없으면 양식을 채우거나 승인한 것처럼 표시하지 않는다.

## 2. 기준선과 목표 고정

1. 개발 담당자·실무자·평가 책임자의 실제 이름과 가용 시간을 기록한다. 한 사람이 여러 역할을 맡을 수 있다.
2. 서로 다른 공고 5건을 선정한다. attributes에 goods, software, technical_evaluation,
   complex_qualification, correction을 전체 집합으로 포함한다. 속성은 중복될 수 있다.
3. 공고와 비교에 사용할 회사자료의 원본 SHA-256 집합, 필요한 자료, 마감 상태, 독립 대조표 위치를 기록한다.
   마감된 공고는 검토용이다. 독립 정답표가 없으면 한계를 기록하고 누락률을 입증했다고 말하지 않는다.
4. 초안까지 잴 2건에만 draft_sample=true를 지정한다. 스캔/재무 표를 점검할 A를 사전에 정한다.
5. 다섯 기준선에 공통 4단계 활동·대기 시간을 초 단위로 입력한다.
   conditions=조건 파악, requirements=요구사항 목록, evidence_search=증빙 검색,
   final_review=제출 전 검토이다. 2건은 draft_seconds/correction_seconds도 입력한다.
6. mandatory_fields는 사전에 확인한 필수 작성 항목 분모이다. populated_fields는 채워진 항목,
   corrected_fields는 사람이 고친 필수 항목이다. 수정한 항목마다 주된 사유를 한 개 부여한다.
   confirmation_required_fields는 채워짐 여부와 별개로 아직 확인이 필요한 필수 항목 수이다.
   readiness_reason_counts에 각 항목의 주된 사유 코드별 건수를 넣고 합계를 일치시킨다.
   예: `{"evidence_unconfirmed": 2, "source_extraction_required": 1}`이면 확인 필요 항목은 3개다.
   코드는 작업대의 `readiness_issues[].code` 계약을 따른다. 확인 필요가 없음을 실제 확인했다면 0과 `{}`를 입력한다.
   미측정은 null로 유지하며, 기준선 미측정이면 목표 고정을 거부하고 개선 행 미측정이면 평가를 미완료로 표시한다.
7. refinds는 위치를 잊어 다시 찾은 횟수다. 의도적인 원문 대조는 제외한다.
   post_pass_omissions는 도구의 검토 통과 이후 발견한 필수 누락이고,
   unsafe_passes는 원문 없는 확정·오래된/잘못된 증빙 유효 판정 등 안전 실패다.
8. 기준선을 보고 목표를 선택한다. 기본 15%/초안 수정 시간 증가 없음/3건 지연 시 중단/재탐색 0회는 제안값이다.
   담당자가 실제로 확정한 뒤 targets_confirmed=true, confirmed_by, 초기 code_revision/rule_version을 기록한다.

```powershell
.venv/Scripts/python.exe -m tools.company_pilot freeze data/company-pilot/2026-09-22
```

이 명령은 모든 기준선과 역할·선정 조건을 검증하고 `protocol-frozen.json`을 만든다.
결과를 이미 입력했거나 미측정이면 거부한다. 출력된 sha256을 improved.json의 protocol_sha256에 넣는다.
이후 보고서는 변경 가능한 pilot.json 대신 고정된 스냅샷을 사용한다.

## 3. A 중간 점검 후 검증 버전 고정

A를 처리하고 최초 관찰 행을 improved.json의 runs에 기록한다. 각 개선 행에는 실제 실행한 code_revision/rule_version이 필요하다.
A는 개발 사례이므로 결과를 검증 4건과 별도로 표시한다. A의 측정 범위 밖에서 한 개발·복구 작업도 별도 작업 기록으로 남긴다.

A에서 스키마/기능 결함을 수정한 뒤, B~E에 사용할 최종 code_revision/rule_version을 improved.json의 최상위 필드에 적는다.

```powershell
.venv/Scripts/python.exe -m tools.company_pilot lock-validation data/company-pilot/2026-09-22
```

이 명령은 A가 완료되고 B~E는 아직 시작하지 않은 시점에 `validation-release.json`을 만든다.
이후 A의 최초 관찰을 덮어쓰거나 B~E에서 다른 코드/규칙을 사용하면 비교를 거부한다.
추가 개발 평가가 필요하면 이전 폴더를 보존하고 새 평가 버전을 만든다.
안전 실패가 있는 A는 검증 단계로 진행하지 않는다.

## 4. 집계

각 행에 시간대가 있는 시작/종료 시각과 동일한 원본 집합·분모를 입력한다.
registry_setup_seconds에는 최초 등록·전사·검토에 든 시간을 기록한다. 단계 시간과 중복 집계하지 않는다.
미완료 건은 성공 행으로 만들지 않고 별도 실무 기록에 장애/자료 미확보 사유를 남긴다.

```powershell
.venv/Scripts/python.exe -m tools.company_pilot report data/company-pilot/2026-09-22
```

| 결과 | 의미 |
|---|---|
| incomplete | 사례·초안 시간·초기 준비 비용 등 필수 관찰이 부족함 |
| hold_safety | 안전 실패/통과 후 필수 누락 발생. 원인 수정과 회귀가 먼저 |
| hold_value | 사전 정한 건수 이상에서 활동 시간이 증가함. 후속 투자 보류 |
| targets_not_met | 측정은 갖췄지만 사전 가치 목표 미달 |
| targets_met | 입력한 관찰이 사전 목표 충족. 제품 전체 실무 검증이나 제출 승인 뜻은 아님 |

전체 5건 중앙값과 B~E 검증 중앙값을 함께 보고한다. 단계별 활동·대기, 수정/작성 시간,
채워진 비율, 수정 비율/사유, 처리자 변경, 관찰 한계, 최초 준비 비용과 절약 시간을 별도로 표시한다.
`[확인 필요]` 비율도 같은 필수 항목 분모로 기준선/개선 결과를 나란히 표시한다. 채워진 칸이라고 확인 완료로 추정하지 않는다.
한글 배치 투자 기준과 독립 원문 대조 결과는 담당자가 실행 계획에 따라 추가 판단한다.
로컬 JSON 해시는 변경 탐지용이며 측정 사실·사람의 신원을 인증하지 않는다.
