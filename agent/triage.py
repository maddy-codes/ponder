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
    "capital of", "chemical symbol", "what year", "plural of", "how many sides",
    "in what year",
)
# Directly-stated computations: long prompt, but one or two operations.
DIRECT = (
    "mg/kg", "per kg", "per hour", "per km", "% of", "vat at", "simple annual interest",
    "per hour for", "to one decimal place", "safety factor", "maximum working load",
)

# --- stakes signals --------------------------------------------------------
# Domain nouns only. "pounds" or "coins" alone is not a stakes signal -- the
# bat-and-ball puzzle is priced in pounds and could not matter less.
CLINICAL = (
    "dose", "mg/kg", "patient", "paediatric", "pediatric", "infusion", "insulin",
    "paracetamol", "drug", "carbohydrate", "body weight", "mg per kg",
)
SAFETY = (
    "safety factor", "bridge", "cable", "coolant", "valve", "reactor", "aircraft",
    "fuel", "worst-case", "rated to", "must close within",
)
FINANCIAL = (
    "vat", "invoice", "payroll", "loan", "interest", "ledger", "closing balance",
    "threshold", "transfer", "tax", "turnover", "turned over", "gross total",
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

    clinical, safety, financial = (_hits(text, g) for g in (CLINICAL, SAFETY, FINANCIAL))
    stakes = 0.12
    if clinical:
        stakes = max(stakes, 0.88 + 0.02 * min(len(clinical), 3))
    if safety:
        stakes = max(stakes, 0.82 + 0.02 * min(len(safety), 3))
    if financial:
        stakes = max(stakes, 0.74 + 0.03 * min(len(financial), 3))
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
    for label, group in (("clinical", clinical), ("safety", safety), ("financial", financial)):
        if group:
            why.append(f"{label}:{group[0]}")
    return Triage(difficulty, stakes, ", ".join(why) or "no strong signals")


_GEMINI_PROMPT = """You are triaging a task for an agent that must decide how much compute to spend.
Score two independent axes from 0 to 1:
- difficulty: how likely a small model is to get this wrong in a single cheap pass.
- stakes: how much damage a wrong answer causes (clinical, financial, safety-critical = high;
  trivia and puzzles = low). Stakes is about consequence, NOT difficulty.
Reply with strict JSON only: {"difficulty": <float>, "stakes": <float>, "rationale": "<12 words>"}

TASK:
"""


def gemini_triage(prompt: str) -> Triage:
    """Optional third partner tech. Same interface; falls back on any failure."""
    import httpx

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={settings.gemini_api_key}"
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
        source="gemini-2.5-flash",
    )


def triage(prompt: str) -> Triage:
    if settings.gemini_api_key:
        try:
            return gemini_triage(prompt)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[triage] gemini judge failed, using heuristic: {exc}")
    return heuristic_triage(prompt)
