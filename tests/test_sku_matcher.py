"""api/sku/matcher.py 단위 테스트.

QdrantStore는 mock 주입. spec_to_query는 순수 함수라 직접 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from api.llm.schemas import ElecSpec
from api.sku.matcher import match_skus, match_skus_from_json, spec_to_query
from api.sku.schemas import AbbSku, SkuMatch


def _mk_match(name: str, score: float) -> SkuMatch:
    return SkuMatch(
        score=score,
        sku=AbbSku(sku_id=f"id-{name}", name=name, category="변압기", description="d"),
    )


class TestSpecToQuery:
    def test_transformer_query(self):
        spec = ElecSpec(
            product_category="변압기",
            phases=3,
            rated_voltage_kv=22.9,
            rated_power_kva=1000.0,
            cooling_type="건식",
        )
        q = spec_to_query(spec)
        assert "변압기" in q
        assert "3상" in q
        assert "22.9kV" in q
        assert "1000.0kVA" in q
        assert "건식" in q

    def test_inverter_query_uses_kw(self):
        spec = ElecSpec(product_category="인버터", rated_power_kw=75.0)
        q = spec_to_query(spec)
        assert "75.0kW" in q

    def test_breaker_query_includes_breaking_capacity(self):
        spec = ElecSpec(
            product_category="차단기",
            rated_current_a=630.0,
            breaking_capacity_ka=25.0,
        )
        q = spec_to_query(spec)
        assert "630.0A" in q
        assert "차단용량 25.0kA" in q

    def test_empty_spec_returns_fallback_query(self):
        q = spec_to_query(ElecSpec())
        assert q == "전기 기자재"

    def test_includes_standards_and_notes(self):
        spec = ElecSpec(
            product_category="변압기",
            standards=["KS C 4306", "IEC 60076"],
            notes="옥내 전용",
        )
        q = spec_to_query(spec)
        assert "KS C 4306" in q
        assert "IEC 60076" in q
        assert "옥내 전용" in q


class TestMatchSkus:
    def test_returns_query_and_matches_from_store(self):
        spec = ElecSpec(product_category="변압기", rated_power_kva=1000.0)
        store = MagicMock()
        store.collection_exists.return_value = True
        store.search.return_value = [_mk_match("A", 0.9), _mk_match("B", 0.7)]

        q, matches = match_skus(spec, limit=5, store=store)
        assert "변압기" in q
        assert len(matches) == 2
        assert matches[0].sku.name == "A"

    def test_empty_collection_returns_no_matches(self):
        store = MagicMock()
        store.collection_exists.return_value = False

        q, matches = match_skus(ElecSpec(product_category="변압기"), store=store)
        assert matches == []
        store.search.assert_not_called()

    def test_match_skus_from_json_parses_correctly(self):
        store = MagicMock()
        store.collection_exists.return_value = True
        store.search.return_value = [_mk_match("X", 0.8)]

        specs_json = '{"product_category": "변압기", "rated_power_kva": 500.0}'
        q, matches = match_skus_from_json(specs_json, limit=3, store=store)

        assert "변압기" in q
        assert "500.0kVA" in q
        assert len(matches) == 1

    def test_match_skus_from_json_handles_invalid_json(self):
        store = MagicMock()
        store.collection_exists.return_value = True
        store.search.return_value = []

        q, matches = match_skus_from_json("not-valid-json", store=store)
        assert q == "전기 기자재"  # fallback for empty spec
        assert matches == []
