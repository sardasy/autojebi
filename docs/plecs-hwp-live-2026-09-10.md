# PLECS HWP 실생성 시도 기록

## 최신 결과: 08:43 실생성 성공

입력 버전 28, 작업 `82611ed7-613e-4792-a6d5-ee3e094b6d03`: 실제 HWP 16쪽, 표 20개, 필드 510개가 생성됐고 모든 저장값을 다시 열어 대조했다. 16쪽 PNG 전체와 한글 프로그램의 표/본문을 직접 확인했다. 이전 버전 27과 실패 기록은 보존했다. 원본 14,514자와 기존 납기 의견 123자는 변경되지 않았다.

결과는 **경고·검토 대기**다. 필수 작성값 누락은 없지만 `[검증필요]`가 남은 필드 18개와 회사 증빙 확인이 필요하다. 내용 승인·제출 준비 완료로 바꾸지 않았다. 산출물·해시·시험 결과·남은 범위는 [최종 검증 기록](hwp-layout-implementation-2026-09-10.md)을 따른다.

아래 내용은 수정하지 않고 남긴 **이전 실패와 복구 이력**이다. 아래의 미완료/승인 요청 중 표시는 당시 시점의 상태다.

## 이전 시도

2026-09-10 KST. 공고 `R26BK01706511-000`, 검증 환경 `3002/8002`, 입력 버전 26.

## 결과

**실제 HWP 생성 미완료.** Worker HTTP 연결 성공과 실제 한글 문서 처리 성공을 구분한다.

| 확인 | 실제 결과 |
|---|---|
| COM 등록 진단 | `hwp_com_registered_activation_unverified` |
| 시작 전 복구 표식 | `recovery_required=false` |
| Worker 시작 | PID 11888, 포트 8000, 토큰 인증 및 기존 허용 폴더 사용 |
| API Worker health | `ok=true`; 파일 처리 성공 증거는 아님 |
| 실제 원문 HWP 읽기 | `/document/analyze-file` 1회, HTTP 504 `operation_uncertain`, `retry_safe=false` |
| 시간 초과 후 큐 | `running=true`, `queued=0`, `generation_verified=false` |
| 한글 프로세스 | PID 42264, `Hwp.exe -Automation -Embedding`, 세션 3, 메인 창 핸들 0 |
| 데스크톱 창 조회 | 한글 및 승인 창이 조회되지 않음. 승인 창이 원인이라고 단정하지 않음 |
| 제안서 템플릿 | `data/templates/제안서_양식.hwp` 없음, 실제 필드 검사도 미완료 |
| v2 생성 시도 | `de541036-991f-46ab-98f6-14fd4c041683`, `blocked/template_path` |

실제 원문 읽기는 기존 제안요청서 사본을 대상으로 했다. 이 HTTP 응답의 시간 초과는 COM 작업 종료를 의미하지 않는다. 추가 COM 요청, 자동 재시도, 레지스트리 변경, 보안 우회, 강제 종료, 복구 표식 해제를 하지 않았다. 사용 중인 3000/8001 환경도 변경하지 않았다.

v2 생성 시도는 템플릿 경로 검사에서 차단되어 PutFieldText를 호출하지 않았다. 저장값 재조회, 생성 파일 해시 및 페이지 배치는 검증하지 못했다. 검토 승인이나 제출 준비 완료를 기록하지 않았다.

## 본문 연결 누락

`data/workspace/preparation/R26BK01706511-000/plecs-bid-draft-20260910.pdf`와 같은 이름의 Markdown은 15쪽 제안서 초안이다. PDF는 작업대에서 `company_reference`로 등록되어 있다.

그러나 `proposal_sections`에는 납기 검토 문단 1개만 있다. 현재 `api/workspace/execution.py`의 `hwp_preview`는 이 섹션들의 본문을 합쳐 `proposal.body`로 전달한다. 따라서 템플릿만 연결해도 기존 15쪽 전체가 자동으로 HWP에 들어가는 것은 아니다. 참고 PDF를 회사·제품 증빙으로 승인하거나 일반 입력값으로 몰래 대체하지 않았다.

## 재개 조건

1. 담당자가 한글/Windows의 초기 설정·파일 접근·복구 창과 기존 파일 상태를 확인한다. 창이 없으면 그 사실부터 확인하고 원인을 진단한다.
2. 실행 중 COM 작업의 종료 여부를 확인한 뒤 기존 복구 절차를 적용한다. 종료되지 않은 작업에 복구 승인을 적용하거나 요청을 중복 전송하지 않는다.
3. DB 매핑과 같은 필드를 가진 실제 제안서 템플릿을 제작한다. 원문 요청서는 템플릿으로 덮어쓰지 않는다.
4. 15쪽 초안을 미승인 상태로 전체 본문에 연결하고 표·한글·페이지 구성을 검토한다. 기존 납기 검토와 원문 인용을 보존한다.
5. 실제 필드 검사, PutFieldText, 저장 파일 재열기, 전체 입력값 대조, 시각 검토를 각각 통과한 뒤 실생성 완료를 판단한다.

공식 데스크톱 API 문서의 CreateField 선언은 [한컴 HwpAutomation_2504.pdf](https://raw.githubusercontent.com/hancom-io/devcenter-archive/main/hwp-automation/HwpAutomation_2504.pdf) 16쪽에서 확인했다. API 문서 확인은 실제 템플릿 제작이나 COM 성공을 대체하지 않는다.

## 07:40 이후 복구 진행

- 담당자가 확인 창이 없음을 확인했고, PID 11888/42264의 제한적 종료 및 복구를 승인했다.
- `data/workspace/recovery-audit/20260909T224048302271Z`에 파일 132개, 작업 79건, 표식 및 매핑 설정을 보존했다.
- 실행 경로와 프로세스 생성시각을 재확인한 뒤 승인된 두 PID만 종료했다. 표식 SHA-256 `9f7fea81520a99453ff90512facf45783fbbebaad3c29dae0caa2a05aa818e73`에 대한 CLI 확인 기록을 보관하고 복구했다.
- Worker를 Windows 사용자 실행 환경에서 PID 63380으로 재시작했다. 기존 토큰, 단일 큐 및 허용 폴더는 유지했다.
- 실제 원문 `/document/analyze-file` 재개 요청은 HTTP 200, 본문 11,553자, `opened/readback/closed/quit`을 반환했다. 원문 해시는 `0f737741b17524dc452d96c43a502ec8d08519a11f8bd8973e5b1edac90dc521`이다. **원문 실연동은 복구됐지만 생성 검증은 아니다.**
- 별도 일회성 템플릿 작성 도구를 기존 RecoveryGuard/COM mutex/SerialQueue로 실행했다. 이 실행은 시간 초과됐고, 작성 프로세스 PID 15060은 종료됐으나 한글 PID 38968이 남았다. 새 HWP 파일이 없는 것을 확인했다. 이 두 번째 실패의 정확한 COM 단계는 확인하지 못했으므로 동일 원인으로 단정하지 않는다.
- 두 번째 실패 상태도 `data/workspace/recovery-audit/20260909T224612871619Z`에 파일 133개 및 작업 79건과 함께 보존했다. PID 38968 종료는 별도로 승인 요청 중이며 표식을 해제하지 않았다.
- 원본 Markdown 14,514자를 `reference-drafts` API로 제안서 1식 작성 요구사항에 연결했다. 기존 납기 검토를 보존하여 섹션 2개, 입력 버전 27이 됐다. 본문 전체가 생성 입력으로 연결되지만 Markdown 표의 HWP 표 변환 및 페이지 배치는 아직 검증하지 않았다. 두 섹션은 pending, 참가 결정도 pending, 제출 준비는 false다. 이 변경에는 LLM 호출이 없다.
