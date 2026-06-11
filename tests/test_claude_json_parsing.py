from api.services.claude_analyzer import extract_first_json_object, safe_parse_json_object


def test_extract_first_json_object_strips_code_fence():
    text = "```json\n{\"a\": 1}\n```"
    assert extract_first_json_object(text) == "{\"a\": 1}"


def test_extract_first_json_object_returns_none_when_missing():
    assert extract_first_json_object("no json here") is None


def test_safe_parse_json_object_fallbacks_to_empty_dict():
    assert safe_parse_json_object("```json\n{not valid}\n```") == {}

