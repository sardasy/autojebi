# HWP Document Engine 1단계

2026-09-23. 범위: 내부 UseCase 분리와 pyhwpx 적용 기반. 라이브러리 교체,
syhwp ingestion, Linux HWPX 생성, PDF 변환 및 운영 전환은 이번 범위에 포함하지 않는다.

## 구현

`api/hwp_worker/use_cases.py`에 다음 내부 작업을 분리했다.

| 작업 | 현재 동작 |
|---|---|
| `inspect_document` | 입력 해시, 문서 열기, 중복을 포함한 필드 목록 |
| `map_fields` | 요청 필드를 존재/누락으로 분리; 누락은 기존 경고 계약 유지 |
| `render_document` | 매핑 값 입력, 새 파일 저장, 닫기 |
| `validate_document` | 저장 파일 해시, 재열기, 필드 순서·중복·모든 저장값 대조 |
| `convert_document` | 검증된 문서 세션으로 기존 PNG 미리보기 생성; PDF 대상은 명시적 거부 |
| `generate_document` | 위 작업 실행 후 출력·템플릿 해시 재대조, 기존 v1 증거 반환 |

Worker HTTP `/document/generate`와 `/document/put-fields`는 같은 핸들러를 사용한다.
요청·응답 필드는 동일하다. 기존 호출자는 이전 주소를 계속 사용한다.
네 개의 내부 작업을 각각 HTTP 엔드포인트로 공개하지 않았다. 중간 문서 상태를
외부 요청 사이에 남기지 않고 전체 생성이 하나의 큐 작업·전역 mutex·COM 소유 세션 안에서 끝난다.
기존 `/document/fields`, `/document/analyze-file`, `/document/create-template`도 유지한다.

`DocumentSession` Protocol은 문서 처리와 구체 라이브러리의 경계다.
현재 `_Session`이 native COM 어댑터다. 세션 생성·종료·CoInitializeEx·mutex는
기존 `_operation`이 소유한다. 변환이나 검증이 실패해도 기존 정리 및 복구 차단을 거친다.
새 UseCase 모듈은 COM이나 pyhwpx를 import하거나 한글을 실행하지 않는다.

저장값 일치, 문서 내 placeholder 검사, 근거에 따른 사실 검증, 사람의 배치 검토는
서로 다르다. 이번 검증은 기존 필드별 저장값·빈값·placeholder 범위를 보존한다.
본문 전체 placeholder, 표 셀 의미, RAG 인용 사실 검증을 완료했다고 표시하지 않는다.

## pyhwpx 연결 조건

2026-09-23 확인한 [공식 소스](https://github.com/martiniifun/pyhwpx/blob/master/pyhwpx/core.py)의
기본 `Hwp()` 생성자는 기존 실행 객체에 연결할 수 있고 `register_module=True`를 사용한다.
보안 모듈 등록 경로에는 레지스트리 등록이 있으며, import 시 COM 캐시 삭제·재생성도 있다.
이는 현재 Worker가 직접 관리하는 소유권·수명과 AGENTS.md의 레지스트리 자동 등록 금지에 맞지 않는다.

따라서 이번에는 pyhwpx 의존성이나 실행 플래그를 추가하지 않았다.
`DocumentSession`은 적용 기반이며 실제 pyhwpx 어댑터 구현·검증 완료를 의미하지 않는다.
후속 어댑터는 버전을 고정하고 다음을 검증해야 한다.

1. Worker가 생성한 COM 객체만 사용하며 사용자 세션을 탐색·재사용하지 않는다.
2. import/초기화/종료가 캐시 삭제·레지스트리 등록·추가 COM 초기화/해제를 수행하지 않는다.
3. CRLF, 중복 필드, void 반환, 저장·재열기, 오류 정리 계약을 유지한다.
4. 기존 실파일 검증 세트와 담당자 배치 대조를 통과한다.

공개 API로 이 조건을 만족하지 못하면 native 어댑터를 유지한다.
`register_module=False` 하나만으로 전체 수명·import 부작용 문제가 해결됐다고 판단하지 않는다.

## 후속 단계의 경계

- [syhwp](https://github.com/sysphere/syhwp/blob/main/README.md)는 HWP/HWPX 텍스트·표를 읽는
  파서다. `api/parsing` 어댑터에서 원문 해시와 위치를 보존하고, 누락 가능성을 검증해야 한다.
  파싱 성공을 사실 검증이나 배치 검증 성공으로 승격하지 않는다.
- [python-hwpx](https://github.com/airmang/python-hwpx/blob/main/README_EN.md)는 순수 Python
  HWPX 편집·생성 엔진이다. 기존 `api/workspace/forms/hwpx_io.py`의 COM 없는 원본 양식
  처리와 역할을 정리한 후 Linux 경로를 연결한다. HWPX 생성만으로 PDF 렌더링이 제공되지는 않는다.
- 기존 요청의 불명확한 실행 상태에 대해 다른 엔진으로 자동 재시도하지 않는다.
  입력 버전·원본 출처·해시·사람 검토·수동 생성 트리거는 기존 정책을 따른다.

## 검증 범위

Fake COM과 Worker HTTP 회귀 테스트로 저장값·해시·중복 필드·CRLF·정리 실패,
두 생성 주소의 직렬화·인증·경로 제한·재시작 복구 차단을 검증한다.
변환은 값 대조 이후 같은 재열기 세션에서만 실행되고, 실패 시 세션을 정리한다.
테스트는 실제 한글 실행이나 pyhwpx 호환성 인증을 대신하지 않는다.

실행 결과: HWP COM·Worker HTTP·서식 제작·저장값·페이지 이미지·줄바꿈·아키텍처
회귀 묶음은 **215 passed, 4 skipped**. `ruff check .`, `lint-imports`의 세 계약,
`git diff --check`도 통과했다. 네 skip은 Windows symlink 권한 부족에 따른 경로 테스트다.
전체 `pytest -q`도 종료 코드 0으로 통과했다(env/권한 게이트 skip 포함).
Starlette deprecated API 및 Qdrant 서버 버전 조회 경고는 남아 있다.
1단계 구현 시에는 실제 한글 문서 생성이나 실행 중 Worker 재시작을 수행하지 않았다.
이후 사용자 요청으로 합성 자료를 이용한 실제 HWP/HWPX 생성·페이지 검증을 완료했다.
실행 범위와 증거는 [기능 테스트 결과](hwp-document-engine-test-2026-09-23.md)를 참고한다.
