"""ProductSpecOutput 또는 CSV row → rdflib.Graph (cat: triples)."""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal
from typing import Iterable
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, XSD

from src.ontology import NS_CAT, NS_SKU, NS_BRAND, NS_CATEGORY, NS_CERT, NS_LICENSE
from src.llm.structured_output import ProductSpecOutput, CertificationSpec

CAT = Namespace(NS_CAT)
SKU_NS = Namespace(NS_SKU)
BRAND_NS = Namespace(NS_BRAND)
CAT_NS_INST = Namespace(NS_CATEGORY)
CERT_NS = Namespace(NS_CERT)
LIC_NS = Namespace(NS_LICENSE)


_SLUG = re.compile(r"[^a-zA-Z0-9\-]+")


def slugify(s: str) -> str:
    s = s.strip().lower().replace(" ", "-")
    return _SLUG.sub("", s)


def sku_uri(sku_id: str) -> URIRef:
    return SKU_NS[slugify(sku_id)]


def brand_uri(brand: str) -> URIRef:
    return BRAND_NS[slugify(brand)]


def category_uri(category: str) -> URIRef:
    return CAT_NS_INST[slugify(category)]


def _bind_prefixes(g: Graph) -> None:
    g.bind("cat", CAT)
    g.bind("exSku", SKU_NS)
    g.bind("exBrand", BRAND_NS)
    g.bind("exCat", CAT_NS_INST)
    g.bind("exCert", CERT_NS)
    g.bind("exLic", LIC_NS)


def build_sku_triples(
    spec: ProductSpecOutput,
    *,
    provenance: str | None = None,
    datasheet_url: str | None = None,
) -> Graph:
    """ProductSpecOutput → Graph (SKU + optional Certifications + Brand/Category 인스턴스).

    Brand/Category 인스턴스가 T-Box 외에 추가되어도 idempotent — Fuseki upload
    는 동일 URI 에 동일 triple 이면 merge 됨.
    """
    g = Graph()
    _bind_prefixes(g)

    sku = sku_uri(spec.sku_id)
    g.add((sku, RDF.type, CAT.SKU))
    g.add((sku, CAT.hasBrand, brand_uri(spec.brand)))
    g.add((brand_uri(spec.brand), RDF.type, CAT.Brand))
    if spec.category:
        g.add((sku, CAT.belongsToCategory, category_uri(spec.category)))
        g.add((category_uri(spec.category), RDF.type, CAT.Category))
    g.add((sku, CAT.modelNumber, Literal(spec.model_number, datatype=XSD.string)))

    for fld, pred in (
        ("voltage_v", CAT.voltageRatingV),
        ("current_a", CAT.currentRatingA),
        ("power_w", CAT.powerRatingW),
        ("switching_freq_hz", CAT.switchingFreqHz),
    ):
        v = getattr(spec, fld)
        if v is not None:
            # rdflib 의 strict xsd:decimal 매핑을 위해 Decimal 사용 (Python float 직접 사용 시 xsd:double 로 인식됨)
            g.add((sku, pred, Literal(Decimal(str(v)), datatype=XSD.decimal)))

    for cert in spec.certifications:
        cert_uri = CERT_NS[slugify(cert.name)]
        g.add((sku, CAT.hasCertification, cert_uri))
        g.add((cert_uri, RDF.type, CAT.Certification))
        g.add((cert_uri, CAT.certifiedBy, Literal(cert.issuer, datatype=XSD.string)))
        if cert.valid_until:
            try:
                d = date.fromisoformat(cert.valid_until)
                g.add((cert_uri, CAT.validUntil, Literal(d, datatype=XSD.date)))
            except ValueError:
                pass  # bad date 무시 (SHACL 에서 잡히지 않으므로 보수적 처리)

    if datasheet_url:
        g.add((sku, CAT.datasheetURL, Literal(datasheet_url, datatype=XSD.anyURI)))
    if provenance:
        g.add((sku, CAT.sourceProvenance, Literal(provenance, datatype=XSD.string)))

    return g


def merge(graphs: Iterable[Graph]) -> Graph:
    out = Graph()
    _bind_prefixes(out)
    for g in graphs:
        for t in g:
            out.add(t)
    return out
