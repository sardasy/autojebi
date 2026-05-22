import pytest
from src.filter.keyword_matcher import KeywordMatcher


@pytest.fixture(scope="module")
def matcher():
    return KeywordMatcher()


def test_core_keyword_high_score(matcher):
    score = matcher.score("변전소 전력설비 교체공사", organization="한국전력공사")
    assert score >= 0.6, f"핵심 키워드 점수가 너무 낮음: {score}"


def test_unrelated_keyword_low_score(matcher):
    score = matcher.score("도로포장 및 보수공사", organization="서울시청")
    assert score < 0.4, f"무관 공고 점수가 너무 높음: {score}"


def test_energy_org_bonus(matcher):
    score_with_org = matcher.score("설비 점검", organization="한국전력공사")
    score_without_org = matcher.score("설비 점검", organization="")
    assert score_with_org > score_without_org
