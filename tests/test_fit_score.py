"""compute_fit_score 휴리스틱 테스트."""

from __future__ import annotations

from api.llm.schemas import ElecSpec
from api.services.claude_analyzer import compute_fit_score


def test_unrelated_returns_zero():
    assert compute_fit_score(ElecSpec(), "비관련") == 0


def test_hil_is_high_fixed_score():
    assert compute_fit_score(ElecSpec(), "HIL") == 75


def test_sw_is_high_fixed_score():
    assert compute_fit_score(ElecSpec(), "SW") == 75


def test_abb장비_with_full_spec_reaches_90():
    spec = ElecSpec(
        product_category="변압기",
        rated_voltage_kv=22.9,
        rated_current_a=630.0,
        rated_power_kva=1000.0,
        quantity=2,
    )
    assert compute_fit_score(spec, "ABB장비") == 90


def test_abb장비_with_only_category_is_at_floor():
    # 5개 핵심 필드 중 1개만 → completeness 0.2 → 60 + 30*0.2 = 66
    spec = ElecSpec(product_category="변압기")
    assert compute_fit_score(spec, "ABB장비") == 66


def test_igbt_partial_spec_mid_range():
    spec = ElecSpec(product_category="IGBT", rated_voltage_kv=1.7, quantity=10)
    # 3/5 채움 → 60 + 30*0.6 = 78
    assert compute_fit_score(spec, "IGBT") == 78


def test_수동소자_scoring_capped_at_70():
    spec = ElecSpec(
        product_category="퓨즈",
        rated_voltage_kv=22.9,
        rated_current_a=100.0,
        rated_power_kva=1.0,
        quantity=10,
    )
    # 5/5 채움 → 50 + 20*1.0 = 70
    assert compute_fit_score(spec, "수동소자") == 70


def test_혼합_low_score_even_with_full_spec():
    spec = ElecSpec(
        product_category="기타",
        rated_voltage_kv=1.0,
        rated_current_a=1.0,
        rated_power_kva=1.0,
        quantity=1,
    )
    # 40 * 1.0 = 40
    assert compute_fit_score(spec, "혼합") == 40


def test_power_kw_alternative_counts_as_filled():
    spec = ElecSpec(
        product_category="인버터",
        rated_voltage_kv=0.38,
        rated_current_a=100.0,
        rated_power_kw=75.0,  # kva 대신 kw
        quantity=1,
    )
    # 5/5 → 60 + 30 = 90
    assert compute_fit_score(spec, "ABB장비") == 90
