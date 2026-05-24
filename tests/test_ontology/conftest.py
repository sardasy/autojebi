"""In-memory rdflib.Graph fixture — CQ A~E 검증용 seed.

부정 케이스 포함:
- abb-power-trafo: ABB 변압기 (CQ_A 의 negative — IGBT 가 아님)
- abb-low-igbt: 100V/50A (CQ_C 의 negative — 임계 미만)
- mitsubishi-relay: 일본 보호계전기 (CQ_A·D·E negative)
- no-cert-sku: 인증 없는 SKU (CQ_E negative)
"""
import pytest
from rdflib import Graph

from src.ontology import (
    CATALOG_TTL, NS_CAT, NS_SKU, NS_BRAND, NS_CATEGORY, NS_CERT, NS_LICENSE,
)
from src.ontology.triple_builder import build_sku_triples
from src.llm.structured_output import ProductSpecOutput, CertificationSpec


def _spec(**kw) -> ProductSpecOutput:
    base = dict(
        sku_id="x", brand="ABB", category="igbt-module", model_number="X",
        voltage_v=None, current_a=None, power_w=None, switching_freq_hz=None,
        certifications=[], datasheet_excerpt="",
    )
    base.update(kw)
    return ProductSpecOutput(**base)


@pytest.fixture(scope="session")
def seed_graph() -> Graph:
    g = Graph()
    g.parse(CATALOG_TTL, format="turtle")

    # CQ_A 정답 set: ABB IGBT 3건
    specs = [
        _spec(sku_id="abb-5sna-1200e330100", brand="ABB", category="igbt-module",
              model_number="5SNA 1200E330100", voltage_v=3300, current_a=1200,
              switching_freq_hz=2000,
              certifications=[CertificationSpec(name="UL 1557", issuer="UL"),
                              CertificationSpec(name="KEPIC-EN", issuer="KEPIC")]),
        _spec(sku_id="abb-5sla-2400e170100", brand="ABB", category="igbt-module",
              model_number="5SLA 2400E170100", voltage_v=1700, current_a=2400,
              switching_freq_hz=2000,
              certifications=[CertificationSpec(name="KEPIC-EN", issuer="KEPIC")]),
        _spec(sku_id="abb-5sna-0750g650300", brand="ABB", category="igbt-module",
              model_number="5SNA 0750G650300", voltage_v=6500, current_a=750,
              switching_freq_hz=1000,
              certifications=[CertificationSpec(name="UL 1557", issuer="UL")]),

        # Infineon 2건 — 1건은 ABB 와 equivalentTo
        _spec(sku_id="infineon-ff1000r17ie4", brand="Infineon", category="igbt-module",
              model_number="FF1000R17IE4", voltage_v=1700, current_a=1000,
              switching_freq_hz=2000,
              certifications=[CertificationSpec(name="UL 1557", issuer="UL")]),
        _spec(sku_id="infineon-fz1500r17hp4", brand="Infineon", category="igbt-module",
              model_number="FZ1500R17HP4", voltage_v=1700, current_a=1500,
              switching_freq_hz=2000),

        # Mitsubishi 1건 (KEPIC 보유 — CQ_E 정답)
        _spec(sku_id="mitsubishi-cm1200ha-66h", brand="Mitsubishi", category="igbt-module",
              model_number="CM1200HA-66H", voltage_v=3300, current_a=1200,
              switching_freq_hz=2000,
              certifications=[CertificationSpec(name="KEPIC-EN", issuer="KEPIC")]),

        # 부정 케이스
        _spec(sku_id="abb-power-trafo", brand="ABB", category="transformer",
              model_number="PowerTrafo-3000", voltage_v=22900, current_a=300),
        _spec(sku_id="abb-low-igbt", brand="ABB", category="igbt-module",
              model_number="LowEnd-100", voltage_v=100, current_a=50,
              switching_freq_hz=5000),
        _spec(sku_id="no-cert-sku", brand="Infineon", category="sic-mosfet",
              model_number="NoCert-001", voltage_v=600, current_a=20),
    ]

    for s in specs:
        for t in build_sku_triples(s, provenance=f"test:{s.sku_id}"):
            g.add(t)

    # equivalentTo: ABB 5SLA 2400E170100 ↔ Infineon FF1000R17IE4 (둘 다 1700V 급)
    from rdflib import URIRef
    g.add((URIRef(NS_SKU + "abb-5sla-2400e170100"),
           URIRef(NS_CAT + "equivalentTo"),
           URIRef(NS_SKU + "infineon-ff1000r17ie4")))
    g.add((URIRef(NS_SKU + "infineon-ff1000r17ie4"),
           URIRef(NS_CAT + "equivalentTo"),
           URIRef(NS_SKU + "abb-5sla-2400e170100")))

    # License: PLECS (CQ_B 정답)
    from rdflib import Literal
    from rdflib.namespace import RDFS, XSD
    from datetime import date
    plecs = URIRef(NS_LICENSE + "plecs-standard-2026")
    g.add((plecs, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
           URIRef(NS_CAT + "License")))
    g.add((plecs, RDFS.label, Literal("PLECS Standard 2026 라이선스", lang="ko")))
    g.add((plecs, URIRef(NS_CAT + "validUntil"),
           Literal(date(2027, 3, 31), datatype=XSD.date)))

    return g


@pytest.fixture(scope="session")
def expected_sku_uris():
    """CQ 별 정답 SKU URI set."""
    return {
        "CQ_A": {NS_SKU + "abb-5sna-1200e330100",
                 NS_SKU + "abb-5sla-2400e170100",
                 NS_SKU + "abb-5sna-0750g650300",
                 NS_SKU + "abb-low-igbt"},  # ABB IGBT 면 다 포함 (스펙 임계 무관)
        "CQ_C": {NS_SKU + "abb-5sna-1200e330100",  # 3300V/1200A
                 NS_SKU + "abb-5sla-2400e170100",  # 1700V/2400A
                 NS_SKU + "abb-5sna-0750g650300",  # 6500V/750A
                 NS_SKU + "infineon-ff1000r17ie4",  # 1700V/1000A
                 NS_SKU + "infineon-fz1500r17hp4",  # 1700V/1500A
                 NS_SKU + "mitsubishi-cm1200ha-66h"},  # 3300V/1200A
        "CQ_D": {(NS_SKU + "abb-5sla-2400e170100",
                  NS_SKU + "infineon-ff1000r17ie4")},
        "CQ_E": {NS_SKU + "abb-5sna-1200e330100",
                 NS_SKU + "abb-5sla-2400e170100",
                 NS_SKU + "mitsubishi-cm1200ha-66h"},
    }
