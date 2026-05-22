from src.filter.energy_keywords import ENERGY_KEYWORDS, WEIGHTS, ENERGY_ORGS

# TF-IDF char ngram은 한국어에서 잡음이 많아 직접 부분문자열 매칭을 사용
_MAX_RAW = sum(WEIGHTS[cat] for cat in WEIGHTS) * 2  # 정규화 기준


class KeywordMatcher:
    def __init__(self):
        self._cat_map: dict[str, str] = {}
        for cat, kws in ENERGY_KEYWORDS.items():
            for kw in kws:
                self._cat_map[kw] = cat

    def score(self, title: str, content: str = "", organization: str = "") -> float:
        text = f"{title} {content}"
        kw_score = self._keyword_score(text)
        meta_bonus = self._meta_bonus(organization)
        return min(1.0, kw_score * 0.8 + meta_bonus * 0.2)

    def _keyword_score(self, text: str) -> float:
        raw = 0.0
        for kw, cat in self._cat_map.items():
            if kw in text:
                raw += WEIGHTS[cat]
        return min(1.0, raw / 3.0)

    def _meta_bonus(self, organization: str) -> float:
        for org in ENERGY_ORGS:
            if org in organization:
                return 0.3
        return 0.0
