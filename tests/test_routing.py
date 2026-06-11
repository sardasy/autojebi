from api.services.routing import assignee_for_category


def test_assignee_mapping():
    assert assignee_for_category("HIL") == "Sangjun"
    assert assignee_for_category("IGBT") == "이용문"
    assert assignee_for_category("ABB장비") == "이용문"
    assert assignee_for_category("비관련") == "미배정"


def test_unknown_category_defaults():
    assert assignee_for_category("UNKNOWN") == "미배정"

