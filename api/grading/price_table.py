"""카테고리 × 정격 → typical 단가 lookup.

abb-bid-pipeline의 app/grading/price_table.py에서 무변경 이식.
ABB SKU 카탈로그에 가격 정보가 없는 상황에서 휴리스틱으로 예가 적정성을 판정한다.
첫 운영 데이터 모이면 영업과 보정 필요.
"""

from __future__ import annotations

from api.llm.schemas import ElecSpec

CATEGORY_ALIASES: dict[str, str] = {
    "몰드변압기": "변압기",
    "유입변압기": "변압기",
    "건식변압기": "변압기",
    "VCB": "차단기",
    "ACB": "차단기",
    "MCCB": "차단기",
    "GCB": "차단기",
    "진공차단기": "차단기",
    "기중차단기": "차단기",
    "배선용차단기": "차단기",
    "가스차단기": "차단기",
    "드라이브": "모터드라이브",
    "VFD": "모터드라이브",
    "인버터드라이브": "모터드라이브",
    "IGBT모듈": "IGBT 모듈",
}


CATEGORY_RATING_FIELD: dict[str, str | None] = {
    "변압기": "rated_power_kva",
    "UPS": "rated_power_kva",
    "인버터": "rated_power_kw",
    "모터드라이브": "rated_power_kw",
    "차단기": "rated_current_a",
    "배전반": None,
    "IGBT 모듈": None,
}


TYPICAL_UNIT_PRICE_KRW: dict[str, dict[tuple[float, float], tuple[int, int]]] = {
    "변압기": {
        (0, 100): (3_000_000, 8_000_000),
        (100, 500): (8_000_000, 25_000_000),
        (500, 1_000): (25_000_000, 60_000_000),
        (1_000, 2_000): (60_000_000, 120_000_000),
        (2_000, 1e9): (120_000_000, 300_000_000),
    },
    "차단기": {
        (0, 600): (5_000_000, 12_000_000),
        (600, 1_200): (10_000_000, 22_000_000),
        (1_200, 1e9): (20_000_000, 50_000_000),
    },
    "인버터": {
        (0, 50): (3_000_000, 10_000_000),
        (50, 200): (10_000_000, 35_000_000),
        (200, 500): (35_000_000, 80_000_000),
        (500, 1e9): (80_000_000, 200_000_000),
    },
    "모터드라이브": {
        (0, 50): (3_000_000, 10_000_000),
        (50, 200): (10_000_000, 35_000_000),
        (200, 500): (35_000_000, 80_000_000),
        (500, 1e9): (80_000_000, 200_000_000),
    },
    "UPS": {
        (0, 10): (2_000_000, 6_000_000),
        (10, 50): (6_000_000, 18_000_000),
        (50, 200): (18_000_000, 50_000_000),
        (200, 1e9): (50_000_000, 200_000_000),
    },
    "배전반": {
        (0, 1e9): (10_000_000, 200_000_000),
    },
    "IGBT 모듈": {
        (0, 1e9): (500_000, 5_000_000),
    },
}


def normalize_category(category: str | None) -> str | None:
    if not category:
        return None
    return CATEGORY_ALIASES.get(category, category)


def lookup_price_range(spec: ElecSpec) -> tuple[int, int] | None:
    """(price_lo, price_hi) per 단가. 카테고리·정격 미지 시 None."""
    cat = normalize_category(spec.product_category)
    if cat is None or cat not in TYPICAL_UNIT_PRICE_KRW:
        return None

    rating_field = CATEGORY_RATING_FIELD.get(cat)
    if rating_field is None:
        bucket = next(iter(TYPICAL_UNIT_PRICE_KRW[cat].values()), None)
        return bucket

    rating = getattr(spec, rating_field, None)
    if rating is None:
        return None

    for (lo, hi), price_range in TYPICAL_UNIT_PRICE_KRW[cat].items():
        if lo <= rating < hi:
            return price_range
    return None
