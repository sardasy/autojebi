"""미림씨스콘 입장에서 한국에너지공과대학교 SST 시험장치 공고를 룰엔진에 입력해
decide_bid() 결과를 출력. unit_cost 3개 시나리오로 비교.

추출된 데이터 (LLM 합본 cap 14000):
- 추정가격: 215,351,400원 (부가세포함)
- 입찰방식: 제한경쟁 + 규격가격동시입찰 (실질: 기술적격 → 최저가)
- 납기: 180일 이내
- 발주기관: 한국에너지공과대학교

회사 프로필 (제안서 발췌):
- 신용등급: BBB-
- 종업원: 24명
- 기술혁신형 중소기업 (Inno-Biz) — is_sme=True
- 매출 147억 (2024)

알 수 없는 값 — 가정 명시:
- 적격심사 배점: LLM이 표 추출 못 함 → default 30/30/10/30
- 낙찰하한율: 이 입찰은 최저가라 N/A — default 0.87745 사용 (룰엔진 모델 호환 위해)
- 납품실적: 회사 ERP 정보 — 빈 리스트로 두면 통과 어려움. SST 관련 실적 200M 1건 가정.
- ISO 인증: 정보 없음 — 빈 리스트
- unit_cost: 미림씨스콘 내부 — 3 시나리오 (70/80/90 %)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.bidding.schemas import (
    TenderRule, EvaluationWeights, CompanyProfile, DeliveryRecord,
)
from src.bidding.decision import decide_bid


# ============================================================================
# 추출 데이터 → 룰엔진 입력
# ============================================================================

TENDER_AMOUNT = 215_351_400  # 추정가격 (부가세 포함)
# 한국 입찰에서 base_price = 추정가격 인 경우 많음. 룰엔진 시뮬을 위해 동일값 사용.
rule = TenderRule(
    base_price=TENDER_AMOUNT,
    nakchal_lower_rate=0.87745,  # 이 입찰은 최저가라 실제 무관. 우리 모델 호환.
)

# 적격심사 배점 — 평가기준서 표가 추출 못 됨 → default
weights = EvaluationWeights()  # 30/30/10/30, 통과 85점

# 미림씨스콘 프로필 (제안서 + 가정)
profile = CompanyProfile(
    recent_3y_delivery_records=[
        # 가정: SST/전력시험장치 분야 실적 1건 (200M)
        DeliveryRecord(
            agency="한국전력공사",
            product_class="전력시험장치",
            amount=200_000_000,
            year=2024,
        ),
    ],
    credit_grade="BBB-",
    debt_ratio=0.45,  # 자기자본 87억 / 총자산 148억 ≈ 41% → 부채비율 약 41/59 ≈ 0.7. 가정 0.45.
    iso_certifications=[],  # 정보 없음
    technical_staff_count=24,
    has_severe_accident=False,
    has_koshams=False,
    converted_to_regular=False,
    parts_localization=False,
    is_sme=True,  # Inno-Biz
)

PRODUCT_CLASS = "전력시험장치"
PRODUCT_CATEGORY = "TYPHOON_HIL"  # RCP+FPGA+SiC 모듈 — 우리 카테고리 중 가장 유사

# ============================================================================
# 3 시나리오 (unit_cost 가정)
# ============================================================================

scenarios = [
    ("저비용 (마진 큼)",      int(TENDER_AMOUNT * 0.70)),  # 150.7M
    ("중간",                int(TENDER_AMOUNT * 0.80)),  # 172.3M
    ("고비용 (마진 작음)",    int(TENDER_AMOUNT * 0.90)),  # 193.8M
]

print(f"{'='*80}\n공고: 한국에너지공과대학교 반도체 변압기(SST) 번들 시험장치 구매")
print(f"추정가격: {TENDER_AMOUNT:,}원\n")

for label, unit_cost in scenarios:
    print(f"\n{'─'*80}\n[시나리오: {label}]  unit_cost = {unit_cost:,}원")
    decision = decide_bid(
        rule=rule,
        weights=weights,
        profile=profile,
        product_class=PRODUCT_CLASS,
        product_category=PRODUCT_CATEGORY,
        tender_amount=TENDER_AMOUNT,
        unit_cost=unit_cost,
    )
    print(f"  recommend         : {decision.recommend}")
    print(f"  strategy          : {decision.strategy}")
    print(f"  추천 응찰가        : {int(decision.bid_price):,}원")
    print(f"  예상 마진율        : {decision.expected_margin_pct*100:.2f}%")
    print(f"  낙찰존 진입 확률   : {decision.win_zone_probability*100:.2f}%")
    print(f"  적격심사 비가격소계: {decision.eligibility_score:.2f}점")
    print(f"  reasons:")
    for r in decision.reasons:
        print(f"    - {r}")

print(f"\n{'='*80}\n[적격심사 detail (시나리오 무관, 동일)]")
last = decision.eligibility_detail
print(f"  납품실적           : {last.delivery_performance:.2f}점")
print(f"  경영상태           : {last.financial_status:.2f}점")
print(f"  기술능력           : {last.technical_capability:.2f}점")
print(f"  신인도             : {last.credibility:.2f}점")
print(f"  가격 제외 소계      : {last.subtotal_without_price:.2f}점")
print(f"  가격에서 필요한 점수: {last.max_price_score_needed:.2f}점")
print(f"  가격 만점 시 통과 가능: {last.passable}")
