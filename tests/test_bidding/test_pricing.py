"""src/bidding/pricing.py 테스트."""
import math

import numpy as np
import pytest

from src.bidding.pricing import (
    SAJEONG_RATES,
    recommend_bid_price,
    simulate_estimated_price,
)
from src.bidding.schemas import TenderRule


def test_simulate_distribution_within_range():
    """예정가격은 ±2% 범위 안에서 산출된 4개의 평균이므로,
    base ± range_pct 안에 매우 높은 확률로 들어와야 한다."""
    rule = TenderRule(base_price=1_000_000)
    samples = simulate_estimated_price(rule, n_sim=10_000, seed=42)

    lower = rule.base_price * (1 - rule.price_range_pct)
    upper = rule.base_price * (1 + rule.price_range_pct)
    in_range = ((samples >= lower) & (samples <= upper)).mean()
    assert in_range >= 0.99, f"{in_range:.4f} samples in range — 분포가 비정상"


def test_strategy_pricing_order():
    """aggressive < balanced < safe (같은 rule 에서)."""
    rule = TenderRule(base_price=1_000_000)
    a = recommend_bid_price(rule, strategy="aggressive", n_sim=2_000, seed=1)
    b = recommend_bid_price(rule, strategy="balanced", n_sim=2_000, seed=1)
    s = recommend_bid_price(rule, strategy="safe", n_sim=2_000, seed=1)
    assert a.bid_price < b.bid_price < s.bid_price


def test_win_zone_nonzero():
    """balanced 전략은 예정가격 분포의 중심에 가까워 ≥30% 확률로 낙찰존 진입."""
    rule = TenderRule(base_price=1_000_000)
    res = recommend_bid_price(rule, strategy="balanced", n_sim=10_000, seed=42)
    assert res.win_zone_probability > 0.3


def test_deterministic_with_seed():
    """동일 seed → 동일 결과 (재현성)."""
    rule = TenderRule(base_price=1_000_000)
    a = simulate_estimated_price(rule, n_sim=1_000, seed=123)
    b = simulate_estimated_price(rule, n_sim=1_000, seed=123)
    np.testing.assert_array_equal(a, b)

    p1 = recommend_bid_price(rule, strategy="balanced", n_sim=1_000, seed=7)
    p2 = recommend_bid_price(rule, strategy="balanced", n_sim=1_000, seed=7)
    assert math.isclose(p1.win_zone_probability, p2.win_zone_probability)
    assert math.isclose(p1.expected_price_mean, p2.expected_price_mean)


def test_p5_p95_bounds():
    """5 백분위 < 평균 < 95 백분위."""
    rule = TenderRule(base_price=1_000_000)
    res = recommend_bid_price(rule, strategy="balanced", n_sim=10_000, seed=42)
    assert res.expected_price_p5 < res.expected_price_mean < res.expected_price_p95


def test_invalid_strategy_raises():
    rule = TenderRule(base_price=1_000_000)
    with pytest.raises(ValueError):
        recommend_bid_price(rule, strategy="moonshot")  # type: ignore[arg-type]


def test_sajeong_rate_constants():
    assert SAJEONG_RATES["aggressive"] < 1 < SAJEONG_RATES["safe"]
    assert SAJEONG_RATES["balanced"] == 1.000
