import pytest

from api.services.status import can_transition, compute_notify_status


@pytest.mark.parametrize(
    ("score", "status"),
    [
        (70, "notified"),
        (100, "notified"),
        (69, "digest_queued"),
        (40, "digest_queued"),
        (39, "archived_low"),
        (0, "archived_low"),
    ],
)
def test_compute_notify_status(score: int, status: str):
    assert compute_notify_status(score) == status


def test_can_transition_happy_path():
    assert can_transition("collected", "analyzed")
    assert can_transition("analyzed", "notified")


def test_can_transition_blocks_invalid():
    assert not can_transition("notified", "analyzed")
    assert not can_transition("collected", "notified")


def test_can_transition_form_filled_path():
    # analyzed can go to form_filled (intermediate) or skip straight to a final state
    assert can_transition("analyzed", "form_filled")
    assert can_transition("analyzed", "notified")

    # form_filled feeds into all three final states
    assert can_transition("form_filled", "notified")
    assert can_transition("form_filled", "digest_queued")
    assert can_transition("form_filled", "archived_low")


def test_can_transition_form_filled_rejects_backwards():
    # cannot regress, cannot loop
    assert not can_transition("form_filled", "analyzed")
    assert not can_transition("form_filled", "form_filled")
    assert not can_transition("collected", "form_filled")

