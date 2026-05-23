"""CQ_A~E 검증 — seed_graph 위에서 SPARQL 실행 → 기대 SKU set 일치."""
from src.ontology.queries import (
    CQ_A_ABB_IGBT, CQ_B_PLECS_LICENSE, CQ_C_HIGH_RATING_IGBT,
    CQ_D_ABB_INFINEON_EQUIVALENTS, CQ_E_KEPIC_SKUS,
)


def test_cq_a_abb_igbt(seed_graph, expected_sku_uris):
    rows = list(seed_graph.query(CQ_A_ABB_IGBT))
    got = {str(r.sku) for r in rows}
    assert got == expected_sku_uris["CQ_A"], (
        f"CQ_A mismatch: missing={expected_sku_uris['CQ_A']-got} extra={got-expected_sku_uris['CQ_A']}"
    )


def test_cq_b_plecs_license_present(seed_graph):
    rows = list(seed_graph.query(CQ_B_PLECS_LICENSE))
    assert len(rows) == 1, f"PLECS 라이선스 1건이어야 함, got {len(rows)}"
    r = rows[0]
    assert "plecs" in str(r.label).lower()
    assert str(r.expiry) == "2027-03-31"


def test_cq_c_high_rating_igbt(seed_graph, expected_sku_uris):
    rows = list(seed_graph.query(CQ_C_HIGH_RATING_IGBT))
    got = {str(r.sku) for r in rows}
    assert got == expected_sku_uris["CQ_C"], (
        f"CQ_C mismatch: missing={expected_sku_uris['CQ_C']-got} extra={got-expected_sku_uris['CQ_C']}"
    )


def test_cq_d_abb_infineon_equivalents(seed_graph, expected_sku_uris):
    rows = list(seed_graph.query(CQ_D_ABB_INFINEON_EQUIVALENTS))
    pairs = {(str(r.ours), str(r.theirs)) for r in rows}
    assert pairs == expected_sku_uris["CQ_D"]


def test_cq_e_kepic_skus(seed_graph, expected_sku_uris):
    rows = list(seed_graph.query(CQ_E_KEPIC_SKUS))
    got = {str(r.sku) for r in rows}
    assert got == expected_sku_uris["CQ_E"]


def test_cq_a_negative_excludes_transformer(seed_graph):
    """ABB 변압기 SKU 는 CQ_A 결과에 들어가면 안 됨 (category mismatch)."""
    rows = list(seed_graph.query(CQ_A_ABB_IGBT))
    got = {str(r.sku) for r in rows}
    assert "https://autojebi.local/data/sku/abb-power-trafo" not in got
