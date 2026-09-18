import pytest

from api.hwp_worker.field_text import mismatch_summary, normalize, wire_text


@pytest.mark.parametrize("value", ["", "\n", "\r", "\r\n", "a\nb\r\nc\rd", " a\t b \n\n"])
def test_wire_preserves_content_and_is_idempotent(value):
    wire = wire_text(value)
    assert normalize(wire) == normalize(value)
    assert wire_text(wire) == wire
    assert "\n" not in wire.replace("\r\n", "")


@pytest.mark.parametrize("expected,actual", [
    ("\n", ""), ("a b", "ab"), ("a\tb", "a b"),
    ("10 kg", "100 kg"), ("not allowed", "allowed"), ("a\n\nb", "a\nb"),
])
def test_content_loss_is_not_normalized_away(expected, actual):
    assert normalize(expected) != normalize(actual)
    detail = mismatch_summary(expected, actual)
    assert all(type(v) is int for v in detail.values())


def test_standalone_newline_loss_is_diagnostic_not_success():
    assert mismatch_summary("\n", "") == {
        "expected_length": 1, "actual_length": 0,
        "expected_linebreaks": 1, "actual_linebreaks": 0,
        "expected_tabs": 0, "actual_tabs": 0, "first_difference": 0,
    }
