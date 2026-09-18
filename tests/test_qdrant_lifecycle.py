"""Store timeout and grading cleanup contracts, without a live Qdrant server."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.sku import qdrant_store
from api.workspace import grading


@pytest.fixture(autouse=True)
def client_factory(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(qdrant_store, "QdrantClient", factory)
    return factory


@pytest.mark.parametrize("api_key", ["", "test-key"])
@pytest.mark.parametrize("explicit", [False, True])
def test_constructor_bounds_timeout_preserves_options_and_compatibility(
    client_factory, monkeypatch, api_key, explicit
):
    monkeypatch.setattr(qdrant_store.settings, "qdrant_url", "http://configured.invalid")
    monkeypatch.setattr(qdrant_store.settings, "qdrant_collection_name", "configured-corpus")
    monkeypatch.setattr(qdrant_store.settings, "qdrant_api_key", api_key)
    store = (
        qdrant_store.QdrantStore("http://explicit.invalid", "explicit-corpus")
        if explicit
        else qdrant_store.QdrantStore()
    )
    try:
        options = client_factory.call_args.kwargs
        client_factory.assert_called_once()
        assert 0 < options["timeout"] <= 10
        assert options["url"] == (
            "http://explicit.invalid" if explicit else "http://configured.invalid"
        )
        assert store.collection == ("explicit-corpus" if explicit else "configured-corpus")
        assert options.get("api_key") == (api_key or None)
        assert options.get("check_compatibility", True) is True
    finally:
        store.close()
    client_factory.return_value.close.assert_called_once_with()


def test_public_close_propagates_client_failure(client_factory):
    store = qdrant_store.QdrantStore()
    error = RuntimeError("close failed")
    client_factory.return_value.close.side_effect = error
    with pytest.raises(RuntimeError) as caught:
        store.close()
    assert caught.value is error
    client_factory.return_value.close.assert_called_once_with()


@pytest.mark.parametrize("failure", [None, "collection", "search", "close"])
def test_grading_uses_public_close_on_success_and_failure(client_factory, monkeypatch, failure):
    store = qdrant_store.QdrantStore()
    client = client_factory.return_value
    client.collection_exists.return_value = True
    client.query.return_value = []
    if failure == "collection":
        client.collection_exists.return_value = False
    elif failure == "search":
        client.query.side_effect = RuntimeError("private-token")
    elif failure == "close":
        client.close.side_effect = RuntimeError("private-token")
    public_close = Mock(wraps=store.close)
    monkeypatch.setattr(store, "close", public_close)
    monkeypatch.setattr(grading, "QdrantStore", lambda: store)
    result = grading._sku_references(
        [{"id": "req", "document_id": "source", "quote": "Original requirement", "locator": "p1"}],
        {"source": {"role": "notice_source", "text": "Original requirement"}},
    )
    public_close.assert_called_once_with()
    client.close.assert_called_once_with()
    assert result["state"] == (
        "unavailable" if failure in {"collection", "search"} else "no_matches"
    )
    assert bool(result["warnings"]) == (failure == "close")
    assert "private-token" not in str(result)


def test_grading_cleanup_supports_legacy_store_doubles(monkeypatch):
    close = Mock()
    store = SimpleNamespace(
        collection="fixture-corpus",
        collection_exists=Mock(return_value=True),
        search=Mock(return_value=[]),
        _client=SimpleNamespace(close=close),
    )
    monkeypatch.setattr(grading, "QdrantStore", lambda: store)
    result = grading._sku_references(
        [{"id": "req", "document_id": "source", "quote": "Original requirement", "locator": "p1"}],
        {"source": {"role": "notice_source", "text": "Original requirement"}},
    )
    close.assert_called_once_with()
    assert result["state"] == "no_matches"
    assert result["warnings"] == []
