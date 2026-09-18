# 검증 환경 DB·파일 백업 복원 기록

## 판정

2026-09-07 검증 환경에서 새 백업과 격리 복원을 실제 실행했다. **부분 검증 통과이며 운영 전환 승인이 아니다.**

| 항목 | 결과 |
|---|---|
| 백업 파일 → 새 폴더 복원 | 112개, 3,266,519 bytes, 개별 SHA256 일치 |
| DB 행 내용 | 30개 테이블, 89개 행 일치 |
| 시퀀스 값/사용 여부 | 18개 일치 |
| 원본/복원 DB 파일 참조 | 34개 동일, 고유 경로 16개 |
| DB 저장 해시 → 백업 파일 | 32개 참조 일치 |
| 백업 누락 | `bid_form`, `proposal` 템플릿 2개. 원래 경로에 실파일 없음 |
| 스키마 비교 | 13개 테이블 CHECK 조건 표현 차이, 엄격 비교 불일치 |
| 전체 판정 | `complete=false`, 운영 전환 차단 유지 |

CHECK 조건 차이는 PostgreSQL 복원 후 형변환 표현이 달라진 사례를 포함한다. 예를 들어 배열 전체의 `::text[]`가 각 원소의 `::text`로 바뀐다. 열·기본키·고유키·외래키·인덱스 조회 결과는 일치했다. 표현 차이를 임의 문자열 치환으로 숨기지 않았으며 전체 조건의 의미 동등성을 통과 판정하지 않았다.

### CHECK 표현 후속 대조

같은 PostgreSQL 16.13에서 31개 CHECK를 다시 대조했다. 원본 스키마가 검증된 ZIP의 기준 지문과 여전히 같은지 먼저 확인했다.
원시 표현이 달랐던 13개 테이블의 20개 조건은 복원 DB에서 `EXPLAIN (VERBOSE, FORMAT JSON)`으로 해석한 출력 식이 모두 같았다. 나머지 11개 조건은 원시 표현 자체가 같았다.
`transform` 허용값을 `none` 하나로 줄인 음성 대조군은 다른 출력 식으로 검출됐다. DB 행·시퀀스·CHECK 외 메타데이터도 다시 일치 확인했다.

결과: 같은 열·타입·서버에서 현재 애플리케이션 조건의 표현 변화라는 설명을 뒷받침한다. 일반 SQL 동등성 증명기는 아니며, 임의 함수가 포함된 외부 스키마를 평가하는 도구로 사용하지 않는다.
읽기 전용 트랜잭션과 5초 제한으로 계획만 확인했으며 `ANALYZE`나 DDL/데이터 변경은 실행하지 않았다.
증거는 `constraint-comparison.json`에 별도 보존했다. 기존 엄격 비교의 `schema_equal=false`, 누락 템플릿, `complete=false` 결과를 덮어쓰지 않았다.

## 실행 범위와 산출물

- 원본: `autojebi_workspace_v2_check`.
- 복원: 새 DB `autojebi_restore_check_20260907_024617`. 기존 DB를 삭제하거나 덮어쓰지 않았다.
- 파일: `data/workspace/backups/paired-20260907-024617/` (Git 제외).
- `bundle.zip`: DB dump, DB 내용/구조 지문, 선택된 원문·업로드·생성물의 실제 바이트와 manifest.
- 백업 SHA256: `76aa3aae77795b7d5c30a6cfd939ba190dfeee7ff9089efff1219304e2cdd53a`.
- `backup-summary.json`: 백업 파일 수·크기·해시.
- `restore-files/`: 새 위치에 복원된 파일. DB에 기록된 기존 절대 경로를 원본 위치로 복사하지 않았다.
- `restore-audit.json`: 최초 검증 결과. 보존했다.
- `restore-audit-detailed.json`: 데이터/스키마/시퀀스/파일 연결을 구분한 후속 결과.

검증 API와 유휴 실행기를 잠시 중지하고 작업이 queued/running 상태가 아닌지 다시 확인한 뒤 `pg_dump -Fc` 및 파일 백업을 실행했다. API와 감독 프로세스는 finally 구문에서 재기동했다. 복원 DB에는 백업 ZIP에서 검증·복원한 dump를 사용했다.

재기동 후 API `/healthz` 정상, Worker idle/available을 확인했다. API PID 50816, 감독 PID 28656, 실행기 PID 107216. 화면 3002는 유지했고 운영 3000/8001 및 기존 3003/8003은 종료하지 않았다.

백업에 포함한 폴더:

- `data/downloads`
- `data/uploads`, `data/exports`
- `data/workspace/uploads`, `data/workspace/exports`
- 해당 실행의 `input/` (DB dump 및 비교 기준)

로그, 과거 백업, 임시 테스트 파일, 실행기 heartbeat/영수증, 설정 비밀값은 포함하지 않았다. 모든 작업이 종료된 검증 환경에 한정한 문서·DB 복원이며, 실행 중 작업의 재해 복구·운영 서버 전체 백업을 대체하지 않는다. 로그 폴더 약 4.68GB는 건드리지 않았으며 별도 보존/회전 정책 검토가 필요하다.

## 검증 도구

코드 검증: 전체 백엔드 **1,063 passed / 13 skipped / 7 warnings** (수집 1,076건), Ruff 및 diff 공백 검사 통과. 새 백업/복원·DB 비교 시험은 80 passed / 4 skipped다. 전체 skip은 PostgreSQL opt-in 4, Windows 링크 권한 8, 실제 HWP opt-in 1이며, Qdrant 클라이언트/서버 버전 경고는 숨기지 않았다. 이 회차에는 프론트 코드를 변경하거나 프론트/E2E 시험을 재실행하지 않았다.

- `api/workspace/file_backup.py`: 명시한 폴더만 스트리밍 ZIP으로 저장한다. 파일 목록·크기·해시를 기록하고 원본을 다시 읽어 도중 변경을 검사한다.
- 기존 출력 및 중첩/동일 원본 루트, 링크/junction, 위험한 파일명, 경로 이탈, 대소문자 충돌, 불일치 ZIP을 거부한다.
- 크기 제한: 파일 100,000개, 총 원문 2GiB, manifest 16MiB. 더 큰 자료는 승인된 분할 백업 정책이 필요하다.
- `restore_backup`은 존재하지 않는 새 폴더에만 복원한다. 중단 시 미완료 표식을 남기며 기존 파일을 삭제하지 않는다.
- `verify_restored`는 복원 보고서 문구를 신뢰하지 않고 실제 바이트와 파일 목록을 다시 검사한다.
- `api/workspace/backup_audit.py`: 기본 스키마의 테이블 행·구조와 PostgreSQL 시퀀스 상태, 알려진 문서 참조를 읽기 전용으로 대조한다. 저장 프로시저·권한·서버 전체 설정 검증은 포함하지 않는다.

도구에는 자동 DB 중지·삭제·환경 전환 기능이 없다. ZIP은 암호화되지 않으므로 회사 원문/증빙과 DB 정보에 맞는 접근 통제 및 별도 보관이 필요하다. 같은 PC의 복사본만으로 디스크 장애 대비가 완료되지는 않는다.

## 재검증 절차

1. 검증 DB와 쓰기 실행기를 명시하고 유휴 상태에서 중지한다. 운영 포트/DB를 추측해 사용하지 않는다.
2. 새 폴더에 DB dump를 만들고 `backup_audit capture`로 지문·참조를 기록한다. `DATABASE_URL`을 명시해야 하며 이 CLI는 `.env`를 자동 읽지 않는다.
3. 명시한 원문/생성물 폴더와 dump 폴더를 `create_backup`에 전달한다. 백업 ZIP 경로는 모든 원본 루트 밖이어야 한다. 생성된 SHA256을 별도로 보관한다.
4. finally 경로로 검증 API/실행기를 재기동하고 health를 확인한다.
5. `restore_backup`으로 새 폴더에 복원하고, 그 안의 dump를 새 DB에 복원한다. 기존 DB/파일 덮어쓰기는 하지 않는다.
6. 복원 DB를 명시하고 `backup_audit verify`에 archive, archive-sha256, restored-root, 복원된 database-audit.json 및 새 output 경로를 전달한다. 전체 불일치의 종료코드는 2다.
7. 누락 템플릿, CHECK 조건 차이, 절대 경로 재연결을 해결하고 재검증한다. 복원 앱을 원본 파일 경로에 연결해 쓰기 시험하지 않는다.

실제 HWP 2종 생성·페이지 배치, LLM 성공, 공고 3건 담당자 대조, 운영 백업 정책과 전환 승인은 별도 미완료 조건이다.
