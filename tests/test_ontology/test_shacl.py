"""SHACL 검증 — 유효 시 conforms=True, 누락 시 conforms=False."""
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, XSD
from src.ontology import NS_CAT, NS_SKU
from src.ontology.validator import validate
from src.ontology.triple_builder import build_sku_triples
from src.llm.structured_output import ProductSpecOutput


def test_valid_sku_conforms():
    spec = ProductSpecOutput(
        sku_id="test-valid", brand="ABB", category="igbt-module",
        model_number="TEST-001", voltage_v=1200, current_a=300,
    )
    g = build_sku_triples(spec)
    conforms, report = validate(g)
    assert conforms, report


def test_sku_missing_brand_fails():
    """brand 누락 → SHACL 위반."""
    g = Graph()
    sku = URIRef(NS_SKU + "broken-1")
    g.add((sku, RDF.type, URIRef(NS_CAT + "SKU")))
    g.add((sku, URIRef(NS_CAT + "modelNumber"), Literal("X-1", datatype=XSD.string)))
    # belongsToCategory + hasBrand 누락
    conforms, report = validate(g)
    assert not conforms
    assert "hasBrand" in report or "Brand" in report


def test_sku_missing_model_number_fails():
    g = Graph()
    sku = URIRef(NS_SKU + "broken-2")
    g.add((sku, RDF.type, URIRef(NS_CAT + "SKU")))
    g.add((sku, URIRef(NS_CAT + "hasBrand"), URIRef("https://autojebi.local/data/brand/abb")))
    g.add((URIRef("https://autojebi.local/data/brand/abb"), RDF.type, URIRef(NS_CAT + "Brand")))
    g.add((sku, URIRef(NS_CAT + "belongsToCategory"),
           URIRef("https://autojebi.local/data/category/igbt-module")))
    g.add((URIRef("https://autojebi.local/data/category/igbt-module"),
           RDF.type, URIRef(NS_CAT + "Category")))
    # modelNumber 누락
    conforms, report = validate(g)
    assert not conforms
    assert "modelNumber" in report
