"""복수예가 메커니즘 몬테카를로 시뮬레이터.

1. 기초금액 ±2% 범위에서 15 개 (n_candidates) 복수예비가격 uniform 추출
2. 그 중 4 개 (n_picked) 를 replace=False 로 무작위 선정
3. 산술평균이 예정가격
4. 위 과정을 n_sim 회 반복하여 예정가격 분포를 얻음

전략별 사정율:
- aggressive 0.985  — 가격 평점 극대화, 마진 축소
- balanced   1.000  — 기초금액 그대로
- safe       1.015  — 마진 확보, 가격 평점 손해

응찰가 = base_price * 사정율 * 낙찰하한율
"""
from __future__ import annotations
from typing import Literal

import numpy as np

from src.bidding.schemas import TenderRule, PricingResult


SAJEONG_RATES: dict[str, float] = {
    "aggressive": 0.985,
    "balanced": 1.000,
    "safe": 1.015,
}


def simulate_estimated_price(
    rule: TenderRule,
    n_sim: int = 100_000,
    seed: int | None = None,
) -> np.ndarray:
    """예정가격 분포 추정.

    벡터화 구현:
    1. (n_sim × n_candidates) 행렬에 ±range 의 uniform 표본
    2. 각 행마다 임의 key 로 argsort 한 뒤 앞 n_picked 인덱스만 선택 (replace=False 와 동치)
    3. 선정된 4 개의 평균

    Returns
    -------
    np.ndarray
        shape ``(n_sim,)`` 의 예정가격 시뮬레이션 결과
    """
    rng = np.random.default_rng(seed)

    lo = rule.base_price * (1 - rule.price_range_pct)
    hi = rule.base_price * (1 + rule.price_range_pct)
    candidates = rng.uniform(lo, hi, size=(n_sim, rule.n_candidates))

    # row 별 무작위 정렬 후 앞 n_picked 만 선택 → replace=False 무작위 추출
    keys = rng.random((n_sim, rule.n_candidates))
    indices = np.argsort(keys, axis=1)[:, : rule.n_picked]
    rows = np.arange(n_sim)[:, None]
    picked = candidates[rows, indices]

    return picked.mean(axis=1)


def recommend_bid_price(
    rule: TenderRule,
    strategy: Literal["aggressive", "balanced", "safe"] = "balanced",
    n_sim: int = 100_000,
    seed: int | None = None,
) -> PricingResult:
    """전략별 응찰가 + 시뮬레이션 통계.

    낙찰존 정의:
        bid_price ≥ 낙찰하한가 (= expected_price × nakchal_lower_rate)
        AND bid_price ≤ expected_price
    위 조건을 만족하는 시뮬레이션 비율이 ``win_zone_probability``.
    """
    if strategy not in SAJEONG_RATES:
        raise ValueError(f"unknown strategy: {strategy!r}. choose from {list(SAJEONG_RATES)}")

    sajeong = SAJEONG_RATES[strategy]
    bid_price = float(rule.base_price * sajeong * rule.nakchal_lower_rate)

    est_prices = simulate_estimated_price(rule, n_sim=n_sim, seed=seed)
    nakchal_lowers = est_prices * rule.nakchal_lower_rate
    in_zone = (bid_price >= nakchal_lowers) & (bid_price <= est_prices)

    return PricingResult(
        bid_price=bid_price,
        expected_price_mean=float(est_prices.mean()),
        expected_price_p5=float(np.percentile(est_prices, 5)),
        expected_price_p95=float(np.percentile(est_prices, 95)),
        nakchal_lower_mean=float(nakchal_lowers.mean()),
        win_zone_probability=float(in_zone.mean()),
    )
