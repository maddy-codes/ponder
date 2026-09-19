"""Triage: score a prompt on difficulty x stakes, from the prompt text alone.

Deliberate constraint: triage sees ONLY the prompt. It never reads `hardness` or
`stakes_tag` from tasks.jsonl -- those are held-out ground truth used by
baselines.py to report error placement. That keeps the demo honest: type a brand
new prompt into Mission Control and triage scores it the same way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from agent.settings import settings


@dataclass
class Triage:
    difficulty: float
    stakes: float
    rationale: str
    source: str = "heuristic"


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [t for t in terms if t in text]


# --- difficulty signals ----------------------------------------------------
# What makes something hard is not length or domain -- it is indirection:
# iteration over time, self-reference, sequences, traps, or writing code.
PUZZLE = (
    "more than the", "one of them is not", "next number in the sequence",
    "each day", "every day", "slips back", "doubles", "shakes hands",
    "sum of all integers", "factorial", "trailing zeros", "how many minutes do",
    "on which day", "first reach",
)
CODE = ("write a python function", "return only the code", "o(log n)")
LOOKUP = (
    "chemical symbol", "stands for", "abbreviation", "normal range", "reference range",
    "generic name", "which vitamin", "how many days in", "what colour",
)
# Directly-stated computations: long prompt, but one or two operations.
DIRECT = (
    "mg/kg", "mcg/kg", "per kg", "ml/kg", "per hour", "ml/hour", "% of", "mg per kg",
    "to one decimal place", "per dose", "units per", "per minute",
)

# --- stakes signals --------------------------------------------------------
# Clinical consequence only. A number is not high-stakes because it is large or
# fiddly -- it is high-stakes because a wrong answer reaches a patient. The ward
# rota puzzles below are genuinely hard and deliberately score LOW here, which is
# the whole point of the hard/low-stakes quadrant.
#
# Three tiers, because "clinical" is not one level of danger. A high-alert drug and
# a paracetamol query are not the same bet, and flattening them would hide the
# judgement the policy is supposed to be making.
HIGH_ALERT = (
    "insulin", "heparin", "warfarin", "morphine", "opioid", "fentanyl", "oxycodone",
    "methotrexate", "chemotherapy", "cytotoxic", "potassium chloride", "digoxin",
    "vancomycin", "gentamicin", "anticoagulant", "thrombolysis",
)
CLINICAL = (
    "dose", "dosage", "mg/kg", "mcg/kg", "patient", "paediatric", "pediatric", "infant",
    "neonate", "neonatal", "child", "infusion", "infuse", "prescribe", "prescribed",
    "drug", "medicine", "medication", "tablet", "body weight", "administer",
    "creatinine", "egfr", "renal", "dialysis", "bolus", "titrate",
)
# Identifiable data is its own axis of consequence: a disclosure harms the patient
# even when every number in the answer is right.
CONFIDENTIAL = (
    "discharge summary", "referral letter", "patient record", "clinic letter",
    "nhs number", "hospital number", "date of birth", "next of kin", "handover",
)


def heuristic_triage(prompt: str) -> Triage:
    text = " ".join(prompt.lower().split())
    words = len(text.split())

    puzzle, code, lookup, direct = (_hits(text, g) for g in (PUZZLE, CODE, LOOKUP, DIRECT))

    difficulty = 0.18
    difficulty += min(0.12, words / 300)          # verbosity is a weak signal, so weight it weakly
    difficulty += 0.22 * min(len(puzzle), 3)      # indirection is the strong one
    difficulty += 0.34 if code else 0.0
    difficulty -= 0.10 * len(lookup)
    difficulty -= 0.08 * min(len(direct), 2)      # explicit rate/unit arithmetic: stated, not inferred
    if re.fullmatch(r"what is \d[\d,.]* ?[-+*/x%] ?\d[\d,.]*\??", text):
        difficulty = 0.05
    difficulty = round(min(0.97, max(0.03, difficulty)), 3)

    high_alert, clinical, confidential = (
        _hits(text, g) for g in (HIGH_ALERT, CLINICAL, CONFIDENTIAL)
    )
    stakes = 0.12
    if clinical:
        stakes = max(stakes, 0.84 + 0.02 * min(len(clinical), 3))
    if confidential:
        stakes = max(stakes, 0.88 + 0.02 * min(len(confidential), 3))
    if high_alert:
        stakes = max(stakes, 0.92 + 0.02 * min(len(high_alert), 3))
    if code:
        stakes += 0.18                            # code gets executed; that raises the floor
    stakes = round(min(0.98, max(0.02, stakes)), 3)

    why = []
    if puzzle:
        why.append(f"indirection({len(puzzle)})")
    if code:
        why.append("writes-code")
    if lookup:
        why.append("lookup")
    if direct:
        why.append("direct-arithmetic")
    for label, group in (
        ("high-alert", high_alert), ("clinical", clinical), ("confidential", confidential)
    ):
        if group:
            why.append(f"{label}:{group[0]}")
    return Triage(difficulty, stakes, ", ".join(why) or "no strong signals")


_GEMINI_PROMPT = """You are triaging a task for an agent that must decide how much compute to spend.
Score two independent axes from 0 to 1:
- difficulty: how likely a small model is to get this wrong in a single cheap pass.
- stakes: how much harm a wrong answer causes a patient. Anything that reaches a patient --
  a dose, an infusion rate, a high-alert drug, identifiable data in a letter -- is high.
  Ward logistics, rota arithmetic and reference lookups are low, however fiddly they are.
  Stakes is about clinical consequence, NOT difficulty.
Reply with strict JSON only: {"difficulty": <float>, "stakes": <float>, "rationale": "<12 words>"}

TASK:
"""


def gemini_triage(prompt: str) -> Triage:
    """Optional third partner tech. Same interface; falls back on any failure."""
    import httpx

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": _GEMINI_PROMPT + prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    resp = httpx.post(url, json=body, timeout=20)
    resp.raise_for_status()
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    return Triage(
        difficulty=round(float(data["difficulty"]), 3),
        stakes=round(float(data["stakes"]), 3),
        rationale=str(data.get("rationale", ""))[:120],
        source=settings.gemini_model,
    )


def triage(prompt: str) -> Triage:
    if settings.gemini_api_key:
        try:
            return gemini_triage(prompt)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[triage] gemini judge failed, using heuristic: {exc}")
    return heuristic_triage(prompt)
