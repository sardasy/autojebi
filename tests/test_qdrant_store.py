"""api/sku/qdrant_store.py 단위 테스트.

QdrantClient를 mock해서 실제 Qdrant 없이도 검증.
fastembed 의존성은 QdrantClient.add()/.query() 내부에서만 사용되므로 mock에선 무관.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.sku.qdrant_store import QdrantStore, _sku_to_text, _stable_id
from api.sku.schemas import AbbSku


def _mk_sku(**overrides) -> AbbSku:
    base = {
        "sku_id": "ABB-X",
        "name": "RESIBLOC",
        "category": "변압기",
        "description": "ABB dry-type",
        "voltage_kv": 22.9,
        "power_kva": 1000.0,
        "phases": 3,
        "cooling_type": "건식",
    }
    base.update(overrides)
    return AbbSku(**base)


class TestSkuToText:
    def test_includes_core_fields(self):
        text = _sku_to_text(_mk_sku())
        assert "RESIBLOC" in text
        assert "변압기" in text
        assert "22.9kV" in text
        assert "1000.0kVA" in text
        assert "3phase" in text
        assert "건식" in text

    def test_inverter_includes_kw(self):
        sku = _mk_sku(power_kva=None, power_kw=75.0)
        text = _sku_to_text(sku)
        assert "75.0kW" in text

    def test_phase1_label(self):
        sku = _mk_sku(phases=1)
        text = _sku_to_text(sku)
        assert "1phase" in text


class TestStableId:
    def test_deterministic(self):
        assert _stable_id("ABB-X") == _stable_id("ABB-X")

    def test_different_inputs_distinct(self):
        assert _stable_id("ABB-X") != _stable_id("ABB-Y")

    def test_returns_uuid_string(self):
        s = _stable_id("X")
        # UUID 표준 길이 (36 chars with hyphens)
        assert len(s) == 36


class TestQdrantStore:
    def test_ingest_calls_add_with_documents(self):
        skus = [_mk_sku(sku_id="A"), _mk_sku(sku_id="B")]

        with patch("api.sku.qdrant_store.QdrantClient") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            store = QdrantStore(url="http://test")
            n = store.ingest(skus)

        assert n == 2
        client.add.assert_called_once()
        kwargs = client.add.call_args.kwargs
        assert len(kwargs["documents"]) == 2
        assert len(kwargs["ids"]) == 2
        # ids는 stable UUID
        assert kwargs["ids"][0] == _stable_id("A")

    def test_ingest_empty_returns_zero(self):
        with patch("api.sku.qdrant_store.QdrantClient"):
            store = QdrantStore(url="http://test")
            assert store.ingest([]) == 0

    def test_search_returns_sku_matches(self):
        with patch("api.sku.qdrant_store.QdrantClient") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            # qdrant query 응답 형태 모사 — metadata + score
            result = MagicMock()
            result.metadata = _mk_sku().model_dump()
            result.score = 0.85
            client.query.return_value = [result]

            store = QdrantStore(url="http://test")
            matches = store.search("변압기 22.9kV", limit=3)

        assert len(matches) == 1
        assert matches[0].sku.name == "RESIBLOC"
        assert matches[0].score == 0.85

    def test_search_skips_invalid_payload(self):
        with patch("api.sku.qdrant_store.QdrantClient") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            good = MagicMock()
            good.metadata = _mk_sku().model_dump()
            good.score = 0.9
            bad = MagicMock()
            bad.metadata = {"sku_id": "Y"}  # missing required fields → validation error
            bad.score = 0.5
            client.query.return_value = [good, bad]

            store = QdrantStore(url="http://test")
            matches = store.search("x", limit=5)

        # bad payload는 스킵
        assert len(matches) == 1

    def test_collection_exists_falls_back_to_false_on_error(self):
        with patch("api.sku.qdrant_store.QdrantClient") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            client.collection_exists.side_effect = Exception("conn refused")

            store = QdrantStore(url="http://test")
            assert store.collection_exists() is False

    def test_count_returns_zero_when_collection_missing(self):
        with patch("api.sku.qdrant_store.QdrantClient") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            client.collection_exists.return_value = False

            store = QdrantStore(url="http://test")
            assert store.count() == 0
