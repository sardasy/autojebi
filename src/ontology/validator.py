"""pyshacl 헬퍼 — data graph + shapes graph → ValidationReport."""
from __future__ import annotations
import logging
from rdflib import Graph
from pyshacl import validate as pyshacl_validate

from src.ontology import CATALOG_TTL, SHAPES_TTL

logger = logging.getLogger(__name__)


def load_shapes() -> Graph:
    g = Graph()
    g.parse(SHAPES_TTL, format="turtle")
    return g


def load_ontology() -> Graph:
    g = Graph()
    g.parse(CATALOG_TTL, format="turtle")
    return g


def validate(data_graph: Graph, *, include_ontology: bool = True) -> tuple[bool, str]:
    """SHACL 검증. (conforms, report_text) 리턴.

    include_ontology=True 면 T-Box 도 함께 로드해 sh:class 등의 검사가
    클래스 정의를 인식하도록 함.
    """
    shapes = load_shapes()
    ontology = load_ontology() if include_ontology else None
    conforms, _report_graph, report_text = pyshacl_validate(
        data_graph,
        shacl_graph=shapes,
        ont_graph=ontology,
        inference="none",
        abort_on_first=False,
        meta_shacl=False,
        advanced=False,
        debug=False,
    )
    return conforms, report_text
