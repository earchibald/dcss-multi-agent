import dcss_api
import pytest

from ladder.conn import classify_error


@pytest.mark.parametrize("text, reason", [
    ("Blocking due to 'more' message.", "more"),
    ("Blocking due to text input necessary from user (likely for level up message).", "text_input"),
    ("Character died.", "died"),
    ("Blocking due to a 'skills to train' txt menu.", "skills"),
    ("Something unexpected", "error:Something unexpected"),
])
def test_classify_api_errors(text, reason):
    assert classify_error(dcss_api.APIErr(text)) == reason


def test_classify_pickup_blocking_error():
    assert classify_error(dcss_api.BlockingErr("Pickup")) == "pickup"
