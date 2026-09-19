"""The rules are data: authored in a file, reloaded live, never a code change."""

import json
import subprocess
import sys
import time

import pytest

from agent.rules import RULES_PATH, load_rules, match_rule


def write(tmp_path, rules):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"version": 1, "rules": rules}))
    return path


BASE = {
    "name": "widget_check",
    "enabled": True,
    "when": {"phrases": ["widget"], "requires_digit": False},
    "then": {"budget": "deep", "sandbox_verify": True, "guardrails": ["units_present"]},
    "reason": "Widgets are load-bearing.",
}


def test_a_rule_is_authored_not_coded(tmp_path):
    rules = load_rules(write(tmp_path, [BASE]))
    assert [r.name for r in rules] == ["widget_check"]
    assert rules[0].guardrails == ("units_present",)
    assert rules[0].match("how many widget units")


def test_disabled_rules_do_not_load(tmp_path):
    assert load_rules(write(tmp_path, [{**BASE, "enabled": False}])) == ()


def test_file_order_is_precedence(tmp_path):
    first = {**BASE, "name": "first", "then": {**BASE["then"], "budget": "deep"}}
    second = {**BASE, "name": "second", "then": {**BASE["then"], "budget": "cheap"}}
    rules = load_rules(write(tmp_path, [first, second]))
    assert rules[0].name == "first"


def test_a_malformed_rule_is_skipped_not_fatal(tmp_path):
    """One bad entry typed in the UI must not take the running agent down."""
    broken = {"name": "", "when": {}, "then": {"budget": "sideways"}}
    rules = load_rules(write(tmp_path, [broken, BASE]))
    assert [r.name for r in rules] == ["widget_check"]


def test_a_rule_with_no_phrases_never_fires(tmp_path):
    empty = {**BASE, "when": {"phrases": [], "requires_digit": False}}
    rules = load_rules(write(tmp_path, [empty]))
    assert not rules[0].match("anything at all")


def test_requires_digit_separates_a_noun_from_a_total(tmp_path):
    rule = load_rules(write(tmp_path, [{**BASE, "when": {"phrases": ["invoice"], "requires_digit": True}}]))[0]
    assert not rule.match("how does an invoice work")
    assert rule.match("invoice 4471 for 1029.00")


def test_a_missing_policy_means_no_policy_applies(tmp_path):
    """Degrades to the numeric thesis rather than failing closed or crashing."""
    assert load_rules(tmp_path / "absent.json") == ()


def test_the_shipped_policy_loads_and_matches():
    assert load_rules(), "agent/rules.json must be the live policy"
    assert match_rule("the dose is 15 mg/kg") is not None


def test_the_editor_reads_what_the_loop_runs():
    """Mission Control asks the agent, so the UI cannot drift from the loader."""
    out = subprocess.run(
        [sys.executable, "-m", "agent.rules", "--json"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(out.stdout)
    assert [r["name"] for r in payload["rules"]] == [r.name for r in load_rules()]
    assert payload["guardrails_available"], "the editor must be offered real guards only"


def test_dry_run_reports_the_match_without_a_model_call():
    out = subprocess.run(
        [sys.executable, "-m", "agent.rules", "--match", "dose of 15 mg/kg"],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(out.stdout)["matched"] == "paediatric_dose"
