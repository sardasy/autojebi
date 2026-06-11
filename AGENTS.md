# AGENTS.md — 미림씨스콘 AI 입찰 자동화 시스템

> 이 파일은 Claude Code 등 코딩 에이전트가 이 프로젝트를 이해하고 작업하기 위한 지침서입니다.
> 사람 개발자도 온보딩 문서로 사용할 수 있습니다.

---

## 1. 프로젝트 개요

미림씨스콘(전력전자 유통: Typhoon HIL, PLECS, ABB IGBT/SCR/Diode, 퓨즈/커패시터/부스바)의
공공조달 입찰 업무를 자동화하는 시스템. 입찰 공고 발생부터 진행 상태 추적까지를
**이벤트 기반 오케스트레이션 파이프라인**으로 처리한다.

핵심 데이터 소스는 KJEBI(입찰 정보 큐레이션 서비스) 알림메일과 나라장터 OpenAPI다.

### 9단계 파이프라인

```
1. 입찰 공고 발생      (KJEBI 메일 / 나라장터 OpenAPI)
2. AI Agent 수집       (n8n 트리거 · 중복제거 · 키워드 필터)
3. 사양/요구사항 분석   (Claude PDF 분석 · 적합도 스코어링)
4. 필요 서류 추출       (자격요건 · 체크리스트 · 위험도)
5. 담당 부서 자동 할당  (카테고리 → 담당자 라우팅)
6. 캘린더 등록         (마감일 · D-3/D-1 리마인더)
7. Slack/Teams 알림    (Graph API · Planner 태스크)
8. 제안서 초안 생성     (슬라이드 라이브러리 · 기술대응표) ※ Human-in-the-loop 게이트
9. 진행 상태 추적       (PostgreSQL 상태머신 · 대시보드)
```

### 개발 단계 (로드맵)

| 단계 | 범위 | 상태 |
|---|---|---|
| 1차 | 1·2·3·7·9 (수집→분석→알림→추적) | G2B OpenAPI 직결 + APScheduler(M1) · n8n KJEBI 메일 경로는 placeholder만(실 운영은 콘솔 /admin 수동 upsert) · claude-haiku-4-5 tool-use 실가동(M2) · 3축 그레이딩 + Qdrant SKU 매칭 + Slack 알림(M3) · Alembic + Docker 풀스택 + healthz DB ping(M4) · 자동 grade 스케줄러 + G2B 자격 API 라이브(M5) · 자격 API 캐싱 24h(M6) · Next.js 읽기전용 프론트 + CORS(M7) · 프론트 액션 통합 + Streamlit 폐기(M8) · X-API-Key 인증 + Vitest/Playwright 테스트(M9) |
| 2차 | 4 (공고 분석기: PDF·체크리스트·위험도·경쟁사 추정) | M2 부분 완료 — ElecSpec 16필드 추출 + G2B 첫 첨부 자동 처리. M3 완료 — score_qual raw JSON 휴리스틱, score_price 정적 룩업. M10 v1 완료 — 서류 자동화(룰+LLM 체크리스트·초안·검증, `analysis.document_automation`). M11 v2 완료 — 파일 업로드 + Excel/HWP 내보내기 (uploads.py/exporters.py). 경쟁사 추정은 M13으로 계획 |
| M12 | KJEBI 메일 paste-UI | 계획 — /admin 메일 본문 paste 입력 + Claude tool-use 추출 → `POST /notices/extract-from-mail` → 기존 upsert 위임. n8n 본격 구현은 실 메일 샘플 확보 후 M12.5 |
| M13 | 경쟁사 추정 | 계획 — `bid_outcomes` 테이블 + `competitor_profiles` Qdrant 컬렉션, grade 응답에 `competitor_signal` 추가. 데이터 소스(G2B 낙찰결과 OpenAPI vs 수동 CSV) Sprint 3 시작 전 확정 |
| 3차 | 8 (제안서 자동화: 템플릿·맞춤화·기술대응표) | 예정 (M14) — `api/routers/proposals.py`, python-pptx, 슬라이드 라이브러리, claude-sonnet-4-5로 모델 전환. 자동 트리거 금지 |
| 4차 | 입찰 전략 AI (낙찰률·경쟁사 패턴·투찰가 추천) | 예정 (M15) — M13 데이터 의존. 휴리스틱 1차 + 학습형 보류. 최종 투찰 자동화 절대 금지 |

---

## 2. 기술 스택

| 레이어 | 기술 | 비고 |
|---|---|---|
| 오케스트레이션 | n8n | 트리거/라우팅/알림. 워크플로우는 JSON으로 버전관리 |
| API 코어 | FastAPI (Python 3.11+) | 상태머신 엔드포인트, 분석 서비스 |
| LLM | Claude API (Anthropic) | 요약·스코어링은 Haiku, 심층분석은 Sonnet, 제안서는 Opus |
| RAG | BGE-M3 + Qdrant | 기존 HTAF RAG 인프라 재활용. 신규 컬렉션만 추가 |
| 데이터 | PostgreSQL | `bid_pipeline` 상태머신 테이블이 시스템 중심 |
| 알림 | Microsoft Graph API / Teams Webhook | Planner 태스크 자동생성 |
| 대시보드 | Next.js 15 (App Router, `frontend/`) | M8에서 Streamlit 폐기, Server Action으로 통합 |
| 문서생성 | python-pptx, WeasyPrint, Gamma API | 제안서·분석리포트 |

### 모델 선택 정책 (비용 최적화)
- **요약/적합도 스코어링 (1차)**: `claude-haiku-4-5` — 대량·저비용
- **PDF 심층 분석 (2차)**: `claude-sonnet-4-5` 또는 상위 모델
- **제안서 작성 (3차)**: 최상위 Opus — 글쓰기 품질 우선
- LLM 호출은 게이트(중복제거 → 키워드필터)를 통과한 건에만. 공고당 1~2회로 제한.

---

## 3. 디렉토리 구조 (권장)

```
milim-bid-automation/
├── AGENTS.md                  # 이 파일
├── n8n/
│   └── milim_bid_alert_workflow.json   # 1·2·3·7단계 워크플로우
├── db/
│   ├── bid_pipeline_schema.sql         # 상태머신 테이블 + 뷰
│   └── migrations/
├── api/                       # FastAPI
│   ├── main.py
│   ├── routers/
│   │   ├── notices.py         # 수집/분석/조회 엔드포인트
│   │   └── proposals.py       # 제안서 생성 (3차)
│   ├── services/
│   │   ├── claude_analyzer.py    # Claude 분석 래퍼
│   │   ├── attachments.py        # G2B 첨부 다운로드/추출 (HWP/PDF)
│   │   ├── document_automation.py # 서류 자동화 v1 (M10) — 체크리스트·초안·검증
│   │   ├── uploads.py            # 서류 자동화 v2 (M11) — 사용자 파일 업로드 저장소
│   │   ├── exporters.py          # 서류 자동화 v2 (M11) — Excel/HWP 내보내기
│   │   └── routing.py            # 담당자 할당 규칙
│   ├── models/                # Pydantic 스키마
│   └── db.py
├── rag/                       # BGE-M3 + Qdrant (2·4차)
│   └── collections/           # bid_history, competitor_profiles 등
├── frontend/                  # Next.js 15 콘솔 (9단계, 운영 UI)
├── slides_library/            # 제안서 슬라이드 풀 (3차)
└── tests/
```

---

## 4. 데이터 백본: 상태머신

모든 단계는 독립 동작하되 `bid_pipeline.status` 한 컬럼으로 묶인다.
각 단계는 이전 status를 조회해 다음 단계만 수행한다 → **멱등성 보장**, 중간 실패 시 멈춘 지점부터 재개.

### 테이블 핵심 컬럼
- `notice_no` (UNIQUE): 공고번호. 중복제거 키.
- `category`: `HIL | SW | IGBT | SCR | 수동소자 | 혼합 | 비관련`
- `fit_score`: 0~100 적합도 (Claude 산출)
- `assignee`: 자동 할당 담당자
- `analysis` (JSONB): Claude 분석 결과 전체 (이후 단계는 이 JSON을 읽기만 함)
- `status`: 생애주기 위치

### 담당자 라우팅 규칙 (5단계)
```python
ROUTING = {
    "HIL":   "Sangjun",            # Typhoon HIL 엔지니어링
    "SW":    "Sangjun",            # PLECS
    "IGBT":  "이용문",              # ABB 반도체 영업
    "SCR":   "이용문",
    "수동소자": "이용문",
    "혼합":   "Sangjun / 이용문",   # 공동
    "비관련": "미배정",
}
```

### 점수별 라우팅 (7단계)
- `fit_score >= 70`: Teams 즉시 알림 + Planner 태스크 → status=`notified`
- `40 <= fit_score < 70`: 일일 다이제스트 큐 → status=`digest_queued`
- `fit_score < 40`: 알림 없이 보관(분석용) → status=`archived_low`

---

## 6. 환경변수 / 시크릿

코드에 시크릿을 하드코딩하지 말 것. 모두 환경변수 또는 n8n 자격증명으로 관리.

| 변수 | 용도 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API (n8n에서는 httpHeaderAuth, 헤더명 `x-api-key`) |
| `G2B_SERVICE_KEY` | 공공데이터포털 나라장터 OpenAPI 인증키 |
| `TEAMS_WEBHOOK_URL` | Teams 채널 수신 커넥터 |
| `DATABASE_URL` | PostgreSQL 접속 (예: `postgresql://user:pw@host:5432/bid`) |
| `QDRANT_URL`, `QDRANT_API_KEY` | RAG (2·4차) |

---

## 7. 빌드 / 실행 / 테스트

```bash
# DB 초기화
psql "$DATABASE_URL" -f db/bid_pipeline_schema.sql

# FastAPI 개발 서버
uvicorn api.main:app --reload --port 8000

# 테스트
pytest -v

# n8n 워크플로우는 n8n UI에서 import:
#   Settings → Import from File → n8n/milim_bid_alert_workflow.json
#   이후 자격증명 3개(Gmail/PostgreSQL/Anthropic) 연결 + 환경변수 2개 설정
```

---

## 8. 코딩 규칙

- **Python**: 3.11+, 타입힌트 필수, Pydantic으로 모든 외부 입출력 스키마 정의.
- **포맷터**: `ruff` + `black` 기준.
- **LLM 응답 파싱**: Claude 응답은 코드펜스(```json)를 제거하고 첫 `{`~마지막 `}` 구간만 파싱.
  파싱 실패 시 기본값 객체로 폴백하고 절대 예외로 파이프라인을 죽이지 말 것.
- **멱등성**: 모든 INSERT는 `ON CONFLICT (notice_no) DO UPDATE` 업서트로.
- **DB 접근**: 단계별 노드는 자기 status 전이만 책임진다. 다른 단계 상태를 건드리지 말 것.
- **에러 처리**: 외부 API 호출(나라장터, Teams)은 타임아웃·재시도 설정. 한 건 실패가 배치 전체를 막지 않도록 item 단위 처리.
- **언어**: 코드·주석은 영어/한국어 혼용 허용. 사용자 대면 알림 텍스트는 한국어.
- **TyphoonTest IDE로 가는 코드는 순수 ASCII** (Typhoon HIL 관련 스크립트 작성 시 — 한글/유니코드 금지). 단, 이 입찰 시스템 코드에는 해당 없음.

---

## 9. 보안 / 안전 가드레일 (중요)

- **Human-in-the-loop 필수 게이트**:
  - 8단계(제안서 생성)는 자동 트리거 금지. 담당자가 참여를 결정한 건만 수동 트리거.
  - 4차 투찰가 추천은 AI가 제안만, 최종 투찰 결정·입력은 반드시 사람이.
- **실제 나라장터 투찰 클릭은 자동화하지 않는다.** 정보 수집·서류 준비·체크리스트 검증까지만 보조.
- **민감 데이터 분리**: 견적·낙찰가·원가는 민감 정보. ZeroSet 등 타 시스템 DB와 분리하거나 별도 스키마/권한.
- **KJEBI 직접 크롤링 금지**: ToS 위반·차단 위험. 알림메일 수신 + 나라장터 OpenAPI 조합만 사용.
- **시크릿**: 절대 커밋 금지. `.env`는 `.gitignore`에.

