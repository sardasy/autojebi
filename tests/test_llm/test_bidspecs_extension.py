"""PR 2: BidSpecs 확장 필드 + validator 회귀."""
import warnings

import pytest

from src.llm.structured_output import BidSpecs


def test_bidspecs_new_fields_optional():
    """모든 새 필드 None/default 로 valid."""
    s = BidSpecs()
    d = s.model_dump()
    assert d["기초금액"] is None
    assert d["낙찰하한율"] is None
    assert d["입찰방식"] == "unknown"
    assert d["낙찰자선정방식"] == "unknown"
    assert d["직접생산증명요구"] is False
    assert d["위임장허용"] is False
    assert d["조달청물품분류번호"] is None
    assert d["적격심사_배점"] is None


def test_price_string_parsing():
    """'850,000,000원' 같은 문자열을 float 로 정규화."""
    s = BidSpecs(추정가격="850,000,000원", 기초금액="3억")  # "3억"은 fallback None
    assert s.추정가격 == 850000000.0
    assert s.기초금액 is None  # parse 실패 → None


def test_nakchal_rate_range():
    """0 < rate <= 1 보장. 1보다 크면 /100 자동 변환."""
    # 이미 소수
    assert BidSpecs(낙찰하한율=0.87745).낙찰하한율 == 0.87745
    # 퍼센트 표기
    assert BidSpecs(낙찰하한율=87.745).낙찰하한율 == 0.87745
    assert BidSpecs(낙찰하한율="87.745%").낙찰하한율 == 0.87745
    # 잘못된 값 → None
    assert BidSpecs(낙찰하한율=0).낙찰하한율 is None
    assert BidSpecs(낙찰하한율=-1).낙찰하한율 is None
    assert BidSpecs(낙찰하한율=999).낙찰하한율 is None
    assert BidSpecs(낙찰하한율="abc").낙찰하한율 is None
    # 빈값 / None
    assert BidSpecs(낙찰하한율=None).낙찰하한율 is None
    # 정규 범위 vs 1 경계
    assert BidSpecs(낙찰하한율=1.0).낙찰하한율 == 1.0
    assert BidSpecs(낙찰하한율=100.0).낙찰하한율 == 1.0


def test_tender_type_whitelist():
    """알 수 없는 값은 unknown 으로 강제."""
    assert BidSpecs(입찰방식="우주방식").입찰방식 == "unknown"
    assert BidSpecs(입찰방식="").입찰방식 == "unknown"
    assert BidSpecs(입찰방식=None).입찰방식 == "unknown"
    assert BidSpecs(입찰방식="일반경쟁").입찰방식 == "일반경쟁"
    assert BidSpecs(입찰방식="MAS").입찰방식 == "MAS"


def test_eval_method_whitelist():
    assert BidSpecs(낙찰자선정방식="적격심사").낙찰자선정방식 == "적격심사"
    assert BidSpecs(낙찰자선정방식="아무거나").낙찰자선정방식 == "unknown"


def test_eligibility_weights_sum_soft_check():
    """배점 dict 합이 100 근처가 아니면 warning (hard fail 아님)."""
    # 정상 합 100
    s1 = BidSpecs(적격심사_배점={"납품실적": 30, "경영상태": 30, "기술능력": 10, "입찰가격": 30})
    total = sum(s1.적격심사_배점.values())
    assert abs(total - 100) < 5  # 100 ± 5 권장

    # 비정상 합 — warn 만, valid 는 유지
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        s2 = BidSpecs(적격심사_배점={"foo": 10, "bar": 20})
        assert s2.적격심사_배점 == {"foo": 10, "bar": 20}


def test_legacy_str_compatibility():
    """기존 specs_json 에 빈문자열로 저장된 값도 None 으로 정규화."""
    s = BidSpecs(공사_용역_유형="", 현장_위치="   ", 납기="")
    assert s.공사_용역_유형 is None
    assert s.현장_위치 is None
    assert s.납기 is None


def test_round_trip_with_legacy_extracted_specs():
    """이전 LLM 추출 결과 (추정가격이 string) 도 valid 하게 로드."""
    legacy = {
        "공고명": "수배전반 교체",
        "발주기관": "한국전력공사",
        "추정가격": "850,000,000원",
        "납기": "120일",
        "입찰마감": "2026-06-15",
        "공사_용역_유형": "공사",
        "주요_기술요건": ["GIS", "디지털 보호계전기"],
        "필수_자격_면허": [],
        "현장_위치": "경기",
    }
    s = BidSpecs.model_validate(legacy)
    assert s.추정가격 == 850000000.0
    assert s.공고명 == "수배전반 교체"
    assert s.기초금액 is None
    assert s.입찰방식 == "unknown"
