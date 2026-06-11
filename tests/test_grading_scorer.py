"""api/grading/scorer.py + qualification.py + price_table.py 단위 테스트."""

from __future__ import annotations

import json

from api.grading.qualification import score_qualification
from api.grading.scorer import combine, score_price, score_spec
from api.llm.schemas import ElecSpec
from api.sku.schemas import AbbSku, SkuMatch


def _mk_match(score: float, sku_id: str = "X") -> SkuMatch:
    return SkuMatch(
        score=score,
        sku=AbbSku(sku_id=sku_id, name="n", category="변압기", description="d"),
    )


class TestScoreSpec:
    def test_none_returns_zero(self):
        assert score_spec(None) == 0.0

    def test_below_noise_floor_clamps_to_zero(self):
        # noise floor = 0.4
        assert score_spec(_mk_match(0.3)) == 0.0

    def test_at_noise_floor_passes(self):
        assert score_spec(_mk_match(0.4)) == 0.4

    def test_clamps_to_one(self):
        assert score_spec(_mk_match(1.5)) == 1.0


class TestScoreQualification:
    def test_none_returns_neutral(self):
        s, notes = score_qualification(None)
        assert s == 0.5
        assert any("없음" in n for n in notes)

    def test_invalid_json_returns_neutral(self):
        s, _ = score_qualification("not json")
        assert s == 0.5

    def test_no_known_keys_returns_neutral(self):
        s, notes = score_qualification(json.dumps({"foo": "bar"}))
        assert s == 0.5
        assert any("자격 키 없음" in n for n in notes)

    def test_negotiated_contract_penalizes(self):
        raw = json.dumps({"cntrctCnclsMthdNm": "수의계약"})
        s, notes = score_qualification(raw)
        assert s < 0.6
        assert any("수의" in n for n in notes)

    def test_designated_bid_penalizes(self):
        raw = json.dumps({"cntrctCnclsMthdNm": "지명입찰"})
        s, _ = score_qualification(raw)
        assert s < 0.6

    def test_open_competition_no_penalty(self):
        raw = json.dumps({"cntrctCnclsMthdNm": "제한경쟁"})
        s, notes = score_qualification(raw)
        assert s == 1.0
        assert any("제한경쟁" in n for n in notes)


class TestScorePrice:
    def test_no_base_price_neutral(self):
        s, note = score_price(ElecSpec(product_category="변압기", quantity=1), None)
        assert s == 0.5
        assert "예가 정보 없음" in note

    def test_unknown_category_neutral(self):
        s, _ = score_price(ElecSpec(product_category="알수없음", quantity=1), 1000000)
        assert s == 0.5

    def test_no_quantity_neutral(self):
        # quantity 미지면 폭락 방지를 위해 중립
        s, _ = score_price(ElecSpec(product_category="변압기", rated_power_kva=1000.0), 5_000_000)
        assert s == 0.5

    def test_in_range_returns_one(self):
        # 변압기 500kVA → bucket (500, 1000): 25M~60M per 대
        # quantity=1, 30M ∈ [25M, 60M]
        spec = ElecSpec(product_category="변압기", rated_power_kva=500.0, quantity=1)
        s, note = score_price(spec, 30_000_000)
        assert s == 1.0
        assert "∈" in note

    def test_below_lower_bound_penalized(self):
        # 1000kVA → bucket (1000, 2000): 60M~120M per 대
        # quantity=1, 10M는 60M보다 한참 미달
        spec = ElecSpec(product_category="변압기", rated_power_kva=1000.0, quantity=1)
        s, _ = score_price(spec, 10_000_000)
        assert 0.0 < s < 0.5

    def test_above_upper_bound_penalized(self):
        # 500kVA → bucket (500, 1000): 25M~60M per 대; 200M 초과
        spec = ElecSpec(product_category="변압기", rated_power_kva=500.0, quantity=1)
        s, _ = score_price(spec, 200_000_000)
        assert 0.0 < s < 0.5

    def test_alias_normalized(self):
        # 몰드변압기 → 변압기 alias 매핑. 200kVA는 (100, 500) 구간 → 8M~25M
        # quantity=1, 5M는 8M 미달
        spec = ElecSpec(product_category="몰드변압기", rated_power_kva=200.0, quantity=1)
        s, _ = score_price(spec, 5_000_000)
        assert 0.0 < s < 0.6

    def test_price_source_label_presmpt(self):
        spec = ElecSpec(product_category="변압기", rated_power_kva=500.0, quantity=1)
        raw = json.dumps({"presmptPrce": "30000000"})
        # 500kVA → 25M~60M; 30M in range → 1.0
        _, note = score_price(spec, 30_000_000, raw)
        assert "presmptPrce" in note


class TestCombine:
    def test_weighted_sum(self):
        b = combine(0.8, 0.6, 0.4, weights={"spec": 0.5, "qualification": 0.3, "price": 0.2})
        # 0.8*0.5 + 0.6*0.3 + 0.4*0.2 = 0.4 + 0.18 + 0.08 = 0.66
        assert abs(b.total - 0.66) < 1e-6
        assert b.spec == 0.8

    def test_hard_gate_qual_zero(self):
        b = combine(0.9, 0.0, 0.9, weights={"spec": 0.5, "qualification": 0.2, "price": 0.3}, hard_gate_qual_zero=True)
        assert b.total == 0.0

    def test_no_hard_gate(self):
        b = combine(0.9, 0.0, 0.9, weights={"spec": 0.5, "qualification": 0.2, "price": 0.3}, hard_gate_qual_zero=False)
        # 0.9*0.5 + 0 + 0.9*0.3 = 0.45 + 0.27 = 0.72
        assert abs(b.total - 0.72) < 1e-6

    def test_uses_settings_default_weights(self):
        # weights=None이면 settings.grade_weights 사용 (기본 0.5/0.2/0.3)
        b = combine(0.5, 0.5, 0.5)
        assert b.weights == {"spec": 0.5, "qualification": 0.2, "price": 0.3}
        # 0.5 * (0.5+0.2+0.3) = 0.5
        assert abs(b.total - 0.5) < 1e-6
