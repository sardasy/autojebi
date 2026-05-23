"""Product/qualification catalog ontology (Phase 1).

T-Box: catalog.ttl (classes, properties)
Shapes: shapes.ttl (SHACL constraints)
"""
from pathlib import Path

ONTOLOGY_DIR = Path(__file__).resolve().parent
CATALOG_TTL = ONTOLOGY_DIR / "catalog.ttl"
SHAPES_TTL = ONTOLOGY_DIR / "shapes.ttl"

# Public prefixes used across queries
NS_CAT = "https://autojebi.local/ontology/catalog#"
NS_BRAND = "https://autojebi.local/data/brand/"
NS_CATEGORY = "https://autojebi.local/data/category/"
NS_SKU = "https://autojebi.local/data/sku/"
NS_LICENSE = "https://autojebi.local/data/license/"
NS_CERT = "https://autojebi.local/data/certification/"

PREFIXES = f"""\
PREFIX cat:     <{NS_CAT}>
PREFIX exBrand: <{NS_BRAND}>
PREFIX exCat:   <{NS_CATEGORY}>
PREFIX exSku:   <{NS_SKU}>
PREFIX exLic:   <{NS_LICENSE}>
PREFIX exCert:  <{NS_CERT}>
PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:     <http://www.w3.org/2002/07/owl#>
PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX schema:  <https://schema.org/>
PREFIX qudt:    <http://qudt.org/schema/qudt/>
PREFIX unit:    <http://qudt.org/vocab/unit/>
"""
