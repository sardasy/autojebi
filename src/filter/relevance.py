"""Phase 2: 키워드+임베딩 점수에 기관별 prior 를 가산 (n_samples >= 5 에서만)."""

PRIOR_MIN_SAMPLES = 5
PRIOR_WEIGHT = 0.15
BASE_WEIGHT = 1.0 - PRIOR_WEIGHT


def combined_score(kw_score: float, emb_score: float, prior: "OrgPrior | None") -> float:
    """Phase 1 base = kw*0.6 + emb*0.4. prior 충분 시 0.15 가중치로 혼합."""
    base = kw_score * 0.6 + emb_score * 0.4
    if prior and prior.n_samples >= PRIOR_MIN_SAMPLES:
        return base * BASE_WEIGHT + prior.p_relevant * PRIOR_WEIGHT
    return base
