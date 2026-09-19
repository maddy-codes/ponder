"""Named domain rules -- the layer that ties a written policy to how hard the model thinks.

Reasoning-effort control is already a shipped API parameter on every major provider,
and checking whether an *answer* complies with policy is already a product category.
Neither one connects a NAMED DOMAIN RULE to how much a model reasons and verifies
BEFORE its answer is trusted. That connection is this file.

**The rules are data, not code.** They live in `agent/rules.json`, are authored by
whoever owns the domain -- in Mission Control's Rules tab or in the file itself --
and this module only loads, validates and compiles them. Nothing here knows what a
dose or an invoice is; that knowledge is in the policy document, where a clinician
or a finance lead can change it without a deploy.

A rule states three things outright, and all three are the audit trail:
  * `budget`         -- how hard to think (outranks the numeric difficulty x stakes score)
  * `sandbox_verify` -- whether the answer must be executed before it is trusted
  * `guardrails`     -- which named checks the answer must clear to be returned at all

Order is precedence: the first enabled rule whose `when` fires decides, so escalating
rules are listed first and a prompt that reads as a casual lookup but mentions a dose
still escalates.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from agent.budget import Budget, Decision
from agent.settings import settings

RULES_PATH = Path(__file__).with_name("rules.json")

_DIGIT = re.compile(r"\d")


def normalise(prompt: str) -> str:
    return " ".join((prompt or "").lower().split())


def _phrase_matcher(terms: tuple[str, ...], requires_digit: bool) -> Callable[[str], bool]:
    """Compile a rule's `when` clause into a matcher.

    Whole-phrase boundaries matter: 'net' must not fire on 'network'. `requires_digit`
    is the difference between a money noun and a money *total* -- there has to be a
    figure present for there to be a number to get wrong.
    """
    if not terms:
        return lambda _text: False
    pattern = re.compile("|".join(rf"(?<!\w){re.escape(t)}(?!\w)" for t in terms))

    def match(text: str) -> bool:
        if not pattern.search(text):
            return False
        return bool(_DIGIT.search(text)) if requires_digit else True

    return match


@dataclass(frozen=True)
class DomainRule:
    name: str
    match: Callable[[str], bool]
    force_budget: Budget
    require_sandbox_verify: bool
    reason: str
    guardrails: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()
    requires_digit: bool = False
    enabled: bool = True

    def to_json(self) -> dict:
        """Round-trips back to the authored form the editor reads and writes."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "when": {"phrases": list(self.phrases), "requires_digit": self.requires_digit},
            "then": {
                "budget": self.force_budget,
                "sandbox_verify": self.require_sandbox_verify,
                "guardrails": list(self.guardrails),
            },
            "reason": self.reason,
        }


def _compile(raw: dict) -> DomainRule | None:
    """One authored rule -> one compiled rule. Returns None for anything malformed.

    A bad rule is skipped rather than raised: the policy file is edited live from the
    UI during a run, and one fat-fingered entry must not take the agent down with it.
    """
    try:
        name = str(raw["name"]).strip()
        when = raw.get("when") or {}
        then = raw.get("then") or {}
        phrases = tuple(
            p.lower().strip() for p in (when.get("phrases") or []) if str(p).strip()
        )
        budget = str(then.get("budget", "deep")).strip()
        if not name or budget not in {"cheap", "deep"}:
            return None
        requires_digit = bool(when.get("requires_digit"))
        return DomainRule(
            name=name,
            match=_phrase_matcher(phrases, requires_digit),
            force_budget=budget,  # type: ignore[arg-type]
            require_sandbox_verify=bool(then.get("sandbox_verify")),
            reason=str(raw.get("reason") or "").strip(),
            guardrails=tuple(str(g) for g in (then.get("guardrails") or [])),
            phrases=phrases,
            requires_digit=requires_digit,
            enabled=bool(raw.get("enabled", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


_cache: dict[str, object] = {"mtime": None, "rules": (), "scope": ()}


def load_rules(path: Path | None = None) -> tuple[DomainRule, ...]:
    """The effective policy, reloaded whenever the file changes underneath us.

    The mtime check is what lets a rule authored in Mission Control take effect on the
    very next task without restarting the agent -- that is the whole point of the rules
    being data. A missing file means no policy applies, and the numeric difficulty x
    stakes score owns every task exactly as it did before rules existed.
    """
    path = path or RULES_PATH
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ()
    if _cache["mtime"] == mtime and path == RULES_PATH:
        return _cache["rules"]  # type: ignore[return-value]

    try:
        raw = json.loads(path.read_text())
        compiled = tuple(
            r for r in (_compile(item) for item in raw.get("rules", [])) if r and r.enabled
        )
        scope = tuple(str(g) for g in (raw.get("scope", {}).get("guardrails") or []))
    except (OSError, json.JSONDecodeError):
        # Keep the last good policy rather than silently dropping to "no rules" mid-run.
        return _cache["rules"]  # type: ignore[return-value]

    if path == RULES_PATH:
        _cache["mtime"], _cache["rules"], _cache["scope"] = mtime, compiled, scope
    return compiled


def scope_guardrails() -> tuple[str, ...]:
    """Guards that apply to EVERY task, matched rule or not.

    A named rule cannot express "and also refuse everything unrelated", because a rule
    only fires on a phrase it recognises -- and an off-topic prompt is precisely the one
    that matches no clinical phrase at all. So scope is declared once for the policy
    rather than repeated on every rule, and it is the only clause that reaches a task no
    rule claimed.
    """
    load_rules()            # populate the cache / honour an edit made since last call
    return _cache["scope"]  # type: ignore[return-value]


def match_rule(prompt: str) -> DomainRule | None:
    """First enabled rule whose match fires, in file order. None means 'no policy applies'."""
    text = normalise(prompt)
    for rule in load_rules():
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
    scope = scope_guardrails()
    rule = match_rule(prompt)
    if rule is None:
        # No policy applies to the *spend*, but scope still does: an unrecognised
        # prompt is exactly the case the scope guard exists for.
        return replace(scored, guardrails=scope + scored.guardrails) if scope else scored

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
        guardrails=scope + rule.guardrails,
    )


def main() -> None:
    """`python -m agent.rules --json` is how Mission Control reads the effective policy.

    The editor never parses rules.json itself: it asks the agent what is actually in
    force, so what you edit is provably what the loop will run.
    """
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Inspect the effective domain policy.")
    ap.add_argument("--json", action="store_true", help="print the effective rules as JSON")
    ap.add_argument("--match", metavar="PROMPT", help="dry-run one prompt against the policy")
    args = ap.parse_args()

    rules = load_rules()

    if args.match is not None:
        rule = match_rule(args.match)
        json.dump(
            {
                "prompt": args.match,
                "matched": rule.name if rule else None,
                "budget": rule.force_budget if rule else None,
                "sandbox_verify": rule.require_sandbox_verify if rule else False,
                "guardrails": list(rule.guardrails) if rule else [],
                "reason": rule.reason if rule else None,
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return

    if args.json:
        from agent.guardrails import catalogue

        json.dump(
            {
                "version": 1,
                "rules": [r.to_json() for r in rules],
                # The editor offers exactly the guards the agent can actually run, so a
                # rule can never name a check that does not exist.
                "guardrails_available": catalogue(),
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    for rule in rules:
        guards = ", ".join(rule.guardrails) or "—"
        print(f"{rule.name:18} {rule.force_budget:5} sandbox={rule.require_sandbox_verify!s:5} guards={guards}")


if __name__ == "__main__":
    main()
