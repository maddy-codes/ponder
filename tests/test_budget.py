"""The budget function is the thesis; it gets tested properly."""

import pytest

from agent.budget import decide
from agent.settings import settings


def test_trivial_stays_cheap():
    d = decide(difficulty=0.1, stakes=0.1)
    assert d.budget == "cheap" and d.reason == "trivial" and d.samples == 1
    assert not d.sandbox


def test_hard_low_stakes_escalates_on_difficulty_only():
    d = decide(difficulty=0.9, stakes=0.1)
    assert d.budget == "deep" and d.reason == "difficulty"
    assert not d.sandbox, "low stakes should not buy executed verification"


def test_easy_high_stakes_escalates_anyway():
    """The money shot: a difficulty router gets exactly this case wrong."""
    d = decide(difficulty=0.15, stakes=0.9)
    assert d.budget == "deep"
    assert d.reason == "stakes-override" and d.is_money_shot
    assert d.sandbox


def test_consequence_buys_width():
    low = decide(difficulty=0.9, stakes=0.1)
    high = decide(difficulty=0.9, stakes=0.9)
    assert high.samples > low.samples


def test_executable_answers_are_always_verified():
    plain = decide(difficulty=0.8, stakes=0.3)
    code = decide(difficulty=0.8, stakes=0.3, executable=True)
    assert not plain.sandbox and code.sandbox


@pytest.mark.parametrize("stakes", [settings.stakes_override - 0.01, settings.stakes_override])
def test_stakes_threshold_is_inclusive(stakes):
    d = decide(difficulty=0.1, stakes=stakes)
    assert (d.budget == "deep") == (stakes >= settings.stakes_override)
