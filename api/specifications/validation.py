"""Exact arithmetic and fail-closed, source-anchored interpretation."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal, localcontext
from functools import lru_cache

from api.specifications.models import Specification

VERSION = "spec-v2"
# Decimal scale factors are explicit; units never imply property equivalence.
UNITS = {
    "s": ("time", "1", "second"), "ms": ("time", ".001", "millisecond"),
    "us": ("time", ".000001", "microsecond"), "μs": ("time", ".000001", "microsecond"),
    "µs": ("time", ".000001", "microsecond"), "ns": ("time", ".000000001", "nanosecond"),
    "Hz": ("frequency", "1", "hertz"), "kHz": ("frequency", "1000", "kilohertz"),
    "MHz": ("frequency", "1000000", "megahertz"),
    "V": ("voltage", "1", "volt"), "kV": ("voltage", "1000", "kilovolt"),
    "A": ("current", "1", "ampere"), "mA": ("current", ".001", "milliampere"),
    "W": ("active_power", "1", "watt"), "kW": ("active_power", "1000", "kilowatt"),
    "VA": ("apparent_power", "1", "volt_ampere"), "kVA": ("apparent_power", "1000", "kilovolt_ampere"),
    "bit": ("resolution", "1", None), "비트": ("resolution", "1", None),
    "채널": ("channels", "1", None), "channel": ("channels", "1", None),
    "개": ("count", "1", None), "seat": ("count", "1", None),
}
PROPERTIES = {
    "time_step": "time", "latency": "time", "sampling_frequency": "frequency",
    "resolution": "resolution", "channels": "channels", "license_count": "count",
    "voltage": "voltage", "current": "current", "active_power": "active_power",
    "apparent_power": "apparent_power",
}
PROPERTY_TERMS = {
    "time_step": ("시간 간격", "time step", "타임스텝"), "latency": ("지연", "latency"),
    "sampling_frequency": ("샘플링", "sampling", "sample rate"),
    "resolution": ("해상도", "resolution"), "channels": ("채널", "channel"),
    "license_count": ("라이선스", "license", "seat"), "voltage": ("전압", "voltage"),
    "current": ("전류", "current"), "active_power": ("유효전력", "active power"),
    "apparent_power": ("피상전력", "apparent power"),
}
NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
QUANTITY = re.compile(rf"(?<![\w.,])(?P<value>{NUMBER})\s*(?P<unit>{'|'.join(sorted(map(re.escape, UNITS), key=len, reverse=True))})(?![A-Za-z가-힣])")
OPS = {"이상": "ge", "초과": "gt", "이하": "le", "미만": "lt"}
NEGATE = {"ge": "lt", "gt": "le", "le": "gt", "lt": "ge"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@lru_cache(maxsize=1)
def unit_registry():
    import pint
    return pint.UnitRegistry(non_int_type=Decimal)


def scale(value: str, unit: str) -> Decimal:
    _, factor, pint_name = UNITS[unit]
    if pint_name:
        # Check the registry, but never round through binary floating point.
        unit_registry().parse_units(pint_name)
    with localcontext() as ctx:
        ctx.prec = 100
        return Decimal(value) * Decimal(factor)


def parse_numeric(raw: str) -> dict:
    matches = list(QUANTITY.finditer(raw))
    if matches and re.search(r"[<>=≤≥]", raw[:matches[0].start()]):
        return {"code": "operator_ambiguous"}
    if matches and re.search(r"않|아니|아닌|아님|제외|\b(?:not|unless|except)\b", raw[:matches[0].start()], re.I):
        return {"code": "condition_requires_review"}
    if len(matches) == 2:
        first, second = matches
        between = raw[first.end():second.start()].strip()
        tail = raw[second.end():].strip().rstrip(".")
        if first["unit"] != second["unit"] or any(v in raw for v in ("제외", "경우", "또는", "아님")):
            return {"code": "condition_requires_review"}
        spread_type = {"±": "uncertainty", "+/-": "uncertainty",
            "측정 불확도 ±": "uncertainty", "허용오차 ±": "tolerance"}.get(between)
        if spread_type and not tail and Decimal(second["value"]) >= 0:
            return {"value": first["value"], "unit": first["unit"], "operator": "eq",
                    spread_type: second["value"]}
        bounds = {"이상": True, "초과": False}
        if between in bounds and tail in {"이하", "미만"} and Decimal(first["value"]) <= Decimal(second["value"]):
            return {"lower": first["value"], "upper": second["value"], "unit": first["unit"],
                    "operator": "range", "lower_inclusive": bounds[between], "upper_inclusive": tail == "이하"}
        return {"code": "quantity_ambiguous"}
    if len(matches) != 1:
        return {"code": "quantity_ambiguous"}
    match = matches[0]
    tail = raw[match.end():].strip().rstrip(".")
    if any(word in raw for word in ("단,", "또는", "제외", "경우", "except", "unless", "±", "+/-")):
        return {"code": "condition_requires_review"}
    operator = "eq" if not tail else OPS.get(tail)
    expression = None
    neg = re.fullmatch(r"(이상|초과|이하|미만)(?:이|은|는)?\s*아님", tail)
    if neg:
        operator = NEGATE[OPS[neg[1]]]
        expression = f"NOT({OPS[neg[1]].upper()}({match['value']}))"
    if not operator:
        return {"code": "operator_ambiguous"}
    return {"value": match["value"], "unit": match["unit"], "operator": operator,
            "expression": expression}


def rdf_check(spec: Specification) -> bool:
    import rdflib
    from pyshacl import validate
    from rdflib.namespace import RDF, XSD
    ns = rdflib.Namespace("urn:autojebi:spec:")
    graph = rdflib.Graph()
    node = rdflib.URIRef("urn:autojebi:item:" + sha(spec.model_dump_json()))
    graph.add((node, RDF.type, ns.Specification))
    for key in ("target", "property", "kind", "unit", "operator", "identifier", "conditions"):
        graph.add((node, ns[key], rdflib.Literal(getattr(spec, key), datatype=XSD.string)))
    for key in ("value", "lower", "upper", "uncertainty", "tolerance"):
        if getattr(spec, key) is not None:
            graph.add((node, ns[key], rdflib.Literal(Decimal(getattr(spec, key)), datatype=XSD.decimal)))
    for key in ("mandatory", "lower_inclusive", "upper_inclusive"):
        graph.add((node, ns[key], rdflib.Literal(getattr(spec, key), datatype=XSD.boolean)))
    graph.add((node, ns.source, rdflib.URIRef("urn:sha256:" + spec.source.text_sha256)))
    graph.add((node, ns.document, rdflib.URIRef("urn:sha256:" + spec.source.document_sha256)))
    graph.add((node, ns.start, rdflib.Literal(spec.source.start, datatype=XSD.integer)))
    graph.add((node, ns.end, rdflib.Literal(spec.source.end, datatype=XSD.integer)))
    graph.add((node, ns.quote, rdflib.Literal(spec.source.quote)))
    shapes = rdflib.Graph().parse(data='''
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix s: <urn:autojebi:spec:> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        s:Shape a sh:NodeShape; sh:targetClass s:Specification;
          sh:property [sh:path s:target; sh:minCount 1; sh:maxCount 1; sh:minLength 1; sh:datatype xsd:string];
          sh:property [sh:path s:property; sh:minCount 1; sh:maxCount 1; sh:minLength 1; sh:datatype xsd:string];
          sh:property [sh:path s:kind; sh:minCount 1; sh:maxCount 1; sh:in ("numeric"^^xsd:string "identifier"^^xsd:string "text"^^xsd:string)];
          sh:property [sh:path s:operator; sh:minCount 1; sh:maxCount 1;
            sh:in ("eq"^^xsd:string "lt"^^xsd:string "le"^^xsd:string "gt"^^xsd:string "ge"^^xsd:string "range"^^xsd:string "unknown"^^xsd:string)];
          sh:property [sh:path s:source; sh:minCount 1; sh:nodeKind sh:IRI];
          sh:property [sh:path s:document; sh:minCount 1; sh:nodeKind sh:IRI];
          sh:property [sh:path s:start; sh:minCount 1; sh:datatype xsd:integer; sh:minInclusive 0; sh:lessThan s:end];
          sh:property [sh:path s:end; sh:minCount 1; sh:datatype xsd:integer];
          sh:property [sh:path s:quote; sh:minCount 1; sh:minLength 1];
          sh:property [sh:path s:uncertainty; sh:maxCount 1; sh:datatype xsd:decimal; sh:minInclusive 0];
          sh:property [sh:path s:tolerance; sh:maxCount 1; sh:datatype xsd:decimal; sh:minInclusive 0];
          sh:or (
            [sh:property [sh:path s:kind; sh:hasValue "numeric"^^xsd:string];
             sh:property [sh:path s:unit; sh:minCount 1; sh:minLength 1];
             sh:or (
               [sh:property [sh:path s:operator; sh:hasValue "range"^^xsd:string];
                sh:property [sh:path s:lower; sh:minCount 1; sh:datatype xsd:decimal; sh:lessThanOrEquals s:upper];
                sh:property [sh:path s:upper; sh:minCount 1; sh:datatype xsd:decimal]]
               [sh:property [sh:path s:value; sh:minCount 1; sh:datatype xsd:decimal]]
             )]
            [sh:property [sh:path s:kind; sh:hasValue "identifier"^^xsd:string];
             sh:property [sh:path s:identifier; sh:minCount 1; sh:minLength 1]]
            [sh:property [sh:path s:kind; sh:hasValue "text"^^xsd:string]]
          ).
        ''', format="turtle")
    return bool(validate(graph, shacl_graph=shapes, advanced=False, inference="none",
                         do_owl_imports=False, js=False)[0])


def validate_spec(spec: Specification, document: dict | None) -> dict:
    codes = []
    doc = document or {}
    text = str(doc.get("text") or "")
    source = spec.source
    if (doc.get("id") != source.document_id or doc.get("sha256") != source.document_sha256
        or sha(text) != source.text_sha256 or text[source.start:source.end] != source.quote):
        codes.append("source_changed")
    if spec.raw != source.quote:
        codes.append("raw_quote_mismatch")
    if spec.target.casefold() not in spec.raw.casefold():
        codes.append("target_unverified")
    extraction = doc.get("extraction") or {}
    structure = extraction.get("table_structure") or {}
    if doc.get("text_origin") != "manual_confirmed" and (
        doc.get("table_structure_status") == "needs_review" or doc.get("ocr_review_required")
        or structure.get("status") in {"needs_review", "partial", "unknown"}
        or any(p.get("review_required") for p in extraction.get("pages", []))
    ):
        codes.append("table_or_ocr_review_required")
    expression = None
    if spec.conditions:
        codes.append("condition_requires_review")
    if spec.kind == "numeric":
        unit = UNITS.get(spec.unit)
        if not unit or PROPERTIES.get(spec.property) != unit[0]:
            codes.append("unit_property_mismatch")
        if not any(term in spec.raw.lower() for term in PROPERTY_TERMS.get(spec.property, ())):
            codes.append("property_unverified")
        parsed = parse_numeric(spec.raw)
        expression = parsed.get("expression")
        if "code" in parsed:
            codes.append(parsed["code"])
        else:
            if parsed["operator"] != spec.operator or parsed["unit"] != spec.unit:
                codes.append("dual_parse_mismatch")
            for key in ("value", "lower", "upper", "uncertainty", "tolerance"):
                expected, actual = parsed.get(key), getattr(spec, key)
                if ((expected is None) != (actual is None) or
                    expected is not None and Decimal(expected) != Decimal(actual)):
                    codes.append("dual_parse_mismatch")
            if spec.operator == "range" and (parsed.get("lower_inclusive") != spec.lower_inclusive
                    or parsed.get("upper_inclusive") != spec.upper_inclusive):
                codes.append("dual_parse_mismatch")
    elif spec.kind == "identifier":
        if spec.property not in {"protocol", "model", "software_version", "license_type"}:
            codes.append("unknown_property")
        if not re.search(r"(?<![\w.\-/])" + re.escape(spec.identifier) + r"(?![\w.\-/])", spec.raw, re.I):
            codes.append("identifier_unverified")
        if spec.operator != "eq" or re.search(r"아님|아닌|제외|않|이상|이하|미만|초과|또는|미지원|불가|없|금지|\b(?:not|unsupported|without|except|unless|cannot)\b", spec.raw, re.I):
            codes.append("identifier_condition_ambiguous")
    else:
        codes.append("unsupported_property")
    try:
        if not rdf_check(spec):
            codes.append("shacl_failed")
    except ImportError:
        codes.append("validator_unavailable")
    except Exception:
        codes.append("validator_failed")
    return {"status": "needs_review" if codes else "valid", "codes": sorted(set(codes)),
            "normalization_version": VERSION, "expression": expression, "tolerance": spec.tolerance or "0"}


def compare(requirement: Specification, evidence: Specification) -> str:
    if (requirement.property != evidence.property or requirement.target != evidence.target
        or requirement.kind != evidence.kind or requirement.conditions or evidence.conditions):
        return "unassessed"
    if requirement.kind == "identifier":
        if requirement.operator != "eq" or evidence.operator != "eq":
            return "unassessed"
        return "meets" if requirement.identifier.casefold() == evidence.identifier.casefold() else "does_not_meet"
    if requirement.kind != "numeric" or evidence.operator != "eq" or requirement.operator == "unknown":
        return "unassessed"
    if requirement.uncertainty is not None or evidence.tolerance is not None:
        return "unassessed"
    if (requirement.unit not in UNITS or evidence.unit not in UNITS or
        UNITS[requirement.unit][0] != UNITS[evidence.unit][0]):
        return "unassessed"
    try:
        center = scale(evidence.value, evidence.unit)
        spread = scale(evidence.uncertainty or "0", evidence.unit)
        with localcontext() as ctx:
            ctx.prec = 100
            lo, hi = center - spread, center + spread
        if requirement.operator == "range":
            lower, upper = scale(requirement.lower, requirement.unit), scale(requirement.upper, requirement.unit)
            li, ui = requirement.lower_inclusive, requirement.upper_inclusive
        else:
            bound = scale(requirement.value, requirement.unit)
            lower = bound if requirement.operator in {"eq", "gt", "ge"} else Decimal("-Infinity")
            upper = bound if requirement.operator in {"eq", "lt", "le"} else Decimal("Infinity")
            li, ui = requirement.operator != "gt", requirement.operator != "lt"
            if requirement.tolerance is not None:
                if requirement.operator != "eq":
                    return "unassessed"
                tolerance = scale(requirement.tolerance, requirement.unit)
                with localcontext() as ctx:
                    ctx.prec = 100
                    lower, upper = bound - tolerance, bound + tolerance
        inside = (lo > lower or li and lo == lower) and (hi < upper or ui and hi == upper)
        outside = hi < lower or (hi == lower and not li) or lo > upper or (lo == upper and not ui)
        return "meets" if inside else "does_not_meet" if outside else "unassessed"
    except (ImportError, KeyError, ValueError, TypeError):
        return "unassessed"
