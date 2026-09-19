"""Named domain rules -- the layer that ties a written policy to how hard the model thinks.

Reasoning-effort control is already a shipped API parameter on every major provider,
and checking whether an *answer* complies with policy is already a product category.
Neither one connects a NAMED DOMAIN RULE to how much a model reasons and verifies
BEFORE its answer is trusted. That connection is this file.

A rule is human-authored, named and auditable. It matches on the prompt -- the same
text triage sees, never the held-out ground truth in tasks.jsonl -- and it states
outright what the match buys: which budget, and whether the answer must be executed
before it is trusted. A matched rule outranks the numeric difficulty x stakes score;
with no match, the score decides exactly as it did before.

Order matters: escalating rules are listed first, so a prompt that reads as a casual
lookup but mentions a dose still escalates.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from agent.budget import Budget, Decision
from agent.settings import settings

_DIGIT = re.compile(r"\d")


def normalise(prompt: str) -> str:
    return " ".join((prompt or "").lower().split())


def _phrases(*terms: str) -> Callable[[str], bool]:
    """Whole-phrase matcher. Boundaries matter: 'net' must not fire on 'network'."""
    pattern = re.compile("|".join(rf"(?<!\w){re.escape(t)}(?!\w)" for t in terms))
    return lambda text: bool(pattern.search(text))


_clinical = _phrases(
    "mg/kg", "mg per kg", "dose", "doses", "dosed", "dosage", "infusion", "insulin",
    "paracetamol", "paediatric", "pediatric", "patient", "body weight", "units of insulin",
)
_safety = _phrases(
    "safety factor", "rated to", "maximum working load", "working load", "coolant",
    "valve", "reactor", "aircraft", "fuel reserve", "must close within", "bridge cable",
    "load-bearing", "worst-case",
)
_financial = _phrases(
    "vat", "invoice", "payroll", "ledger", "balance", "closing balance", "gross total",
    "gross amount", "turnover", "turned over", "simple annual interest", "loan",
    "registration threshold", "total cost", "amount owed", "net amount", "transfer",
)
_lookup = _phrases(
    "capital of", "chemical symbol", "plural of", "how many sides", "in what year",
    "what year", "who wrote", "who painted", "abbreviation for",
)


def _financial_total(text: str) -> bool:
    """A money noun alone is not a total -- there has to be a figure to get wrong."""
    return _financial(text) and bool(_DIGIT.search(text))


@dataclass(frozen=True)
class DomainRule:
    name: str
    match: Callable[[str], bool]
    force_budget: Budget
    require_sandbox_verify: bool
    reason: str


DOMAIN_RULES: tuple[DomainRule, ...] = (
    DomainRule(
        name="clinical_dose",
        match=_clinical,
        force_budget="deep",
        require_sandbox_verify=True,
        reason="Dosing arithmetic is recomputed and executed before it is trusted, "
               "however simple the sum looks.",
    ),
    DomainRule(
        name="safety_margin",
        match=_safety,
        force_budget="deep",
        require_sandbox_verify=True,
        reason="Load, tolerance and timing margins are verified by execution -- a "
               "plausible-looking number is the failure mode here.",
    ),
    DomainRule(
        name="financial_total",
        match=_financial_total,
        force_budget="deep",
        require_sandbox_verify=True,
        reason="Financial totals are always deep-verified regardless of apparent difficulty.",
    ),
    DomainRule(
        name="casual_lookup",
        match=_lookup,
        force_budget="cheap",
        require_sandbox_verify=False,
        reason="Casual factual lookups never warrant deep reasoning.",
    ),
)


def match_rule(prompt: str) -> DomainRule | None:
    """First rule whose match fires, in declaration order. None means 'no policy applies'."""
    text = normalise(prompt)
    for rule in DOMAIN_RULES:
        if rule.match(text):
            return rule
    return None


def apply(prompt: str, scored: Decision, executable: bool = False) -> Decision:
    """Put the named rule above the score.

    Returns `scored` untouched when no rule matches, so the difficulty x stakes
    thesis still owns every unpoliced task. When a rule does match, the returned
    Decision records which rule decided and -- if the rule disagreed with the
    score -- what the score alone would have spent. That difference is the whole
    point: it is the audit trail for "the policy, not the classifier, chose this".
    """
    rule = match_rule(prompt)
    if rule is None:
        return scored

    budget = rule.force_budget
    sandbox = budget == "deep" and (rule.require_sandbox_verify or executable)
    # A forced escalation still buys the standard deep width; a task the score had
    # already widened (high stakes) keeps the wider fan-out it earned.
    samples = 1 if budget == "cheap" else max(scored.samples, settings.deep_samples)

    why = rule.reason
    if budget != scored.budget:
        why += f" (the score alone would have spent {scored.budget})"

    return Decision(
        budget=budget,
        reason=scored.reason,      # the scored reason is kept; the rule is a layer above it
        sandbox=sandbox,
        samples=samples,
        matched_rule=rule.name,
        rule_reason=why,
    )
