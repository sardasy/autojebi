"""ElecSpec/title → autojebi Category 매핑 테스트."""

from __future__ import annotations

from api.llm.schemas import ElecSpec
from api.services.claude_analyzer import map_elec_to_category


def test_empty_spec_no_title_is_unrelated():
    assert map_elec_to_category(ElecSpec(), None) == "비관련"
    assert map_elec_to_category(ElecSpec(), "") == "비관련"


def test_title_keyword_hil_wins_over_empty_spec():
    assert map_elec_to_category(ElecSpec(), "Typhoon HIL 시뮬레이터 구매") == "HIL"
    assert map_elec_to_category(ElecSpec(), "HIL platform") == "HIL"


def test_title_keyword_plecs_routes_to_sw():
    assert map_elec_to_category(ElecSpec(), "PLECS 라이선스") == "SW"


def test_title_keyword_overrides_elec_spec_category():
    # HIL이 제목에 있으면 ElecSpec.product_category와 무관하게 HIL
    spec = ElecSpec(product_category="변압기")
    assert map_elec_to_category(spec, "Typhoon HIL 시험기") == "HIL"


def test_igbt_routes_to_igbt():
    assert map_elec_to_category(ElecSpec(product_category="IGBT 모듈"), "공고") == "IGBT"
    assert map_elec_to_category(ElecSpec(product_category="igbt"), "공고") == "IGBT"


def test_scr_routes_to_scr():
    assert map_elec_to_category(ElecSpec(product_category="SCR 제어기"), "공고") == "SCR"


def test_abb_hardware_routes_to_abb장비():
    for pc in ("변압기", "차단기", "UPS", "인버터", "모터드라이브", "배전반"):
        assert (
            map_elec_to_category(ElecSpec(product_category=pc), "공고") == "ABB장비"
        ), f"{pc} should map to ABB장비"


def test_passive_components_route_to_수동소자():
    for pc in ("퓨즈", "커패시터", "콘덴서", "부스바"):
        assert (
            map_elec_to_category(ElecSpec(product_category=pc), "공고") == "수동소자"
        ), f"{pc} should map to 수동소자"


def test_passive_english_keywords():
    assert (
        map_elec_to_category(ElecSpec(product_category="Fuse for switchboard"), "공고")
        == "수동소자"
    )
    assert (
        map_elec_to_category(ElecSpec(product_category="Busbar assembly"), "공고")
        == "수동소자"
    )


def test_unknown_category_falls_back_to_혼합():
    assert map_elec_to_category(ElecSpec(product_category="기타 전기설비"), "공고") == "혼합"
