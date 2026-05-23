"""Competency Question SPARQL constants.

테스트 fixture (in-memory graph) 와 라이브 Fuseki 둘 다에서 동일하게 실행.
변경 시 CQ 테스트가 즉시 깨지도록 락 — 의도된 회귀만 통과.
"""
from src.ontology import PREFIXES


# CQ_A: ABB 브랜드의 IGBT 모듈 SKU 목록
CQ_A_ABB_IGBT = PREFIXES + """
SELECT ?sku ?model WHERE {
  ?sku a cat:SKU ;
       cat:hasBrand exBrand:abb ;
       cat:belongsToCategory exCat:igbt-module ;
       cat:modelNumber ?model .
}
ORDER BY ?sku
"""


# CQ_B: PLECS 라이선스 보유 여부 + 만료일
# (rdfs:label 에 'plecs' 포함된 License 인스턴스)
CQ_B_PLECS_LICENSE = PREFIXES + """
SELECT ?license ?label ?expiry WHERE {
  ?license a cat:License ;
           rdfs:label ?label ;
           cat:validUntil ?expiry .
  FILTER(CONTAINS(LCASE(STR(?label)), "plecs"))
}
"""


# CQ_C: 450V/100A 이상 IGBT 모듈 SKU
CQ_C_HIGH_RATING_IGBT = PREFIXES + """
SELECT ?sku ?v ?a WHERE {
  ?sku a cat:SKU ;
       cat:belongsToCategory exCat:igbt-module ;
       cat:voltageRatingV ?v ;
       cat:currentRatingA ?a .
  FILTER(?v >= 450 && ?a >= 100)
}
ORDER BY DESC(?v) DESC(?a)
"""


# CQ_D: Infineon SKU 중 우리 ABB SKU와 동등성능을 가진 경쟁 제품 페어
CQ_D_ABB_INFINEON_EQUIVALENTS = PREFIXES + """
SELECT ?ours ?theirs WHERE {
  ?ours    cat:hasBrand exBrand:abb ;
           cat:equivalentTo ?theirs .
  ?theirs  cat:hasBrand exBrand:infineon .
}
ORDER BY ?ours
"""


# CQ_E: KEPIC 인증 보유 SKU 목록
# 발급기관 literal 이 xsd:string 으로 저장되므로 str() 캐스팅 비교로 일관성 확보.
CQ_E_KEPIC_SKUS = PREFIXES + """
SELECT DISTINCT ?sku WHERE {
  ?sku cat:hasCertification ?c .
  ?c   cat:certifiedBy ?issuer .
  FILTER(STR(?issuer) = "KEPIC")
}
ORDER BY ?sku
"""


ALL_CQS = {
    "CQ_A": CQ_A_ABB_IGBT,
    "CQ_B": CQ_B_PLECS_LICENSE,
    "CQ_C": CQ_C_HIGH_RATING_IGBT,
    "CQ_D": CQ_D_ABB_INFINEON_EQUIVALENTS,
    "CQ_E": CQ_E_KEPIC_SKUS,
}
