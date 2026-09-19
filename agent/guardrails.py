"""Pydantic AI guardrails for clinical answers, selected by the domain rule that matched.

Ponder's rules already said *how hard to think* and *whether to execute the answer*.
This module adds the third clause: **which named checks the answer must clear before
it is allowed to leave**. All three come from the same authored rule, so one policy
document controls effort, verification and compliance together.

The domain is medication safety, and the guards encode published clinical standards
rather than generic "is this output nice" heuristics:

* `safe_dose_notation` implements the ISMP *Do Not Use* abbreviation list -- a trailing
  zero ("1.0 mg" misread as 10 mg) and a naked decimal (".5 mg" misread as 5 mg) are
  documented tenfold-overdose mechanisms, not style preferences.
* `no_patient_identifiers` validates NHS numbers with the Modulus 11 checksum the NHS
  actually specifies, so a ten-digit lab value is not mistaken for an identifier.

Two layers, both first-party Pydantic:

1. **Per model call** -- `pydantic_ai_harness.guardrails.InputGuardrail` and
   `OutputGuardrail` are attached to the worker `Agent` via `capabilities=[...]`.
   The framework runs them on every request, redacts secrets and personal data out of
   the prompt before it is sent, and turns a failed output check into a real
   `ModelRetry` so the model fixes its own answer. These produce their own Logfire
   spans, so a guardrail firing is visible in the same trace as the tokens it cost.

2. **On the aggregated answer** -- `check()` runs the same guard functions once more
   over the answer best-of-N actually settled on, because that string is the one the
   caller receives and no per-call guard ever saw it.

The second layer is where Ponder differs from a compliance filter. A guardrail trip is
not only a rejection, it is **evidence the task was underfunded**: `loop.py` responds by
escalating the budget and re-running rather than returning a refusal. Spending more
compute is a valid answer to "this output isn't good enough", and it is the answer a
difficulty router can never give, because it has already decided the task was easy.

**This layer is not the gateway.** These guards run inside our own process, on our own
agent. Stopping patient data from *reaching* a model is a separate control that belongs
at the Pydantic AI Gateway, where the request is cleaned before it leaves the boundary;
see `docs/GATEWAY_GUARDRAILS.md`. The two are complementary, and neither substitutes for
the other: the gateway cleans what goes in, this module polices what comes out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from pydantic_ai_harness.guardrails import (
    GuardrailResult,
    InputGuardrail,
    OutputGuardrail,
    detectors,
)

Guard = Callable[[object], GuardrailResult]

# A number, including 1,234.56 and .5 and negatives.
_NUMBER = re.compile(r"-?(?:\d[\d,]*\.?\d*|\.\d+)")
# Units a clinical answer has to carry: mass, volume, amount-of-substance, activity,
# rate and time. Whole-token only: "min" must not fire inside "minimum", and "m" must
# not fire inside "them" -- the trailing `(?!\w)` does that work. The leading guard
# forbids a *letter* before the unit but deliberately allows a digit, because a unit
# flush against its figure ("270mg", "250ms", "20%") is ordinary prescribing notation;
# `(?<!\w)` rejected all of those, and "%" could never match at all since a percentage
# is always written against its figure. Trailing punctuation is left alone on purpose --
# rejecting the unit in "The dose is 270 mg." would send a good answer back for a retry.
_UNITS = re.compile(
    r"(?<![A-Za-z_])(?:"
    r"mg|mcg|microgram|micrograms|g|gram|grams|kg|ng|"
    r"ml|mls|millilitre|millilitres|l|litre|litres|"
    r"mmol|mol|meq|mosmol|"
    r"units?|iu|international units?|"
    r"tablets?|capsules?|doses?|puffs?|drops?|vials?|ampoules?|"
    r"mg/kg|mcg/kg|ml/kg|mg/kg/day|mg/kg/hour|mcg/kg/min|ml/hour|ml/hr|units/hour|"
    r"mmhg|kpa|bpm|"
    r"s|ms|sec|secs|second|seconds|min|mins|minute|minutes|"
    r"h|hr|hrs|hour|hours|day|days|week|weeks|"
    r"c|f|°c|°f|%"
    r")(?!\w)",
    re.I,
)
# Hedges that have no business on an answer someone will act on. Deliberately short:
# a guard that fires on ordinary prose burns compute for nothing.
_HEDGE = re.compile(
    r"(?<!\w)(?:i think|i believe|i'm not sure|im not sure|not certain|not entirely sure|"
    r"roughly|approximately|approx\.|around about|might be|may be about|probably|"
    r"should be around|cannot be certain|unsure)(?!\w)",
    re.I,
)


def _text(output: object) -> str:
    """The string a guard should inspect.

    `OutputGuardrail` hands over the output unchanged, so a typed output arrives as the
    model instance. `str(MyModel(...))` would give a repr that hides field contents from
    a regex, so a Pydantic output is serialised to JSON instead.
    """
    dump = getattr(output, "model_dump_json", None)
    return dump() if callable(dump) else str(output)


# --------------------------------------------------------------------------- guards


def numeric_answer_present(output: object) -> GuardrailResult:
    """A dose question answered with prose is not answered."""
    if _NUMBER.search(_text(output)):
        return GuardrailResult.allow()
    return GuardrailResult.retry(
        "This question has a numeric answer and your response contains no number. "
        "Give the figure explicitly on the last line."
    )


def units_present(output: object) -> GuardrailResult:
    """A dose without its unit is the classic fatal near-miss."""
    text = _text(output)
    if not _NUMBER.search(text) or _UNITS.search(text):
        return GuardrailResult.allow()
    return GuardrailResult.retry(
        "Your answer states a quantity with no unit. Restate it with the unit attached "
        "(for example '270 mg', not '270')."
    )


def no_hedging(output: object) -> GuardrailResult:
    """A dose is committed or it is re-derived -- never hedged."""
    hedge = _HEDGE.search(_text(output))
    if hedge is None:
        return GuardrailResult.allow()
    return GuardrailResult.retry(
        f"Your answer hedges ('{hedge.group(0)}'). This task is governed by a rule that "
        "does not accept an approximate dose. Recompute it and state the exact value."
    )


# ---------------------------------------------------------- ISMP Do Not Use list

# Each entry: (name, pattern, what to write instead). These are the abbreviations and
# notations the ISMP lists as implicated in real, repeated medication errors -- every
# one of them is a documented tenfold or wrong-drug mechanism, which is why this guard
# retries rather than tidies the text up silently.
_NOTATION_FAULTS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "trailing zero",
        # "1.0 mg" -- if the decimal point is missed this reads as 10 mg.
        re.compile(r"(?<![\d.])\d+\.0(?!\d)"),
        "drop the trailing zero: write '1 mg', never '1.0 mg'",
    ),
    (
        "naked decimal",
        # ".5 mg" -- if the point is missed this reads as 5 mg.
        re.compile(r"(?<![\d.])\.\d"),
        "use a leading zero: write '0.5 mg', never '.5 mg'",
    ),
    (
        "U for units",
        # "10U" / "10 u" -- the U is read as a zero, giving a tenfold insulin overdose.
        re.compile(r"\d\s*[Uu](?![a-zA-Z])"),
        "spell it out: write '10 units', never '10U'",
    ),
    (
        "IU",
        re.compile(r"(?<![A-Za-z])IU(?![a-zA-Z])"),
        "write 'international units', never 'IU' (read as IV or 10)",
    ),
    (
        "microgram symbol",
        re.compile(r"(?<![A-Za-z])(?:µg|ug)(?![a-zA-Z])"),
        "write 'mcg', never 'µg' or 'ug' (read as mg -- a thousandfold error)",
    ),
    (
        "latin frequency",
        re.compile(r"(?<![A-Za-z])(?:Q\.?D|QOD|Q\.?O\.?D|OD|OU)(?![a-zA-Z])"),
        "write the frequency out: 'daily', 'every other day'",
    ),
)


def safe_dose_notation(output: object) -> GuardrailResult:
    """Reject notations the ISMP lists as causes of tenfold dosing errors.

    A correct number written unsafely is still a medication error -- "1.0 mg" and
    ".5 mg" are both read tenfold wrong when the decimal point is lost to a fax, a
    photocopy or a handwritten transcription. So this checks *how* the dose is written,
    not whether the arithmetic was right, and it is the one guard here that can fail an
    answer whose value is perfectly correct.
    """
    text = _text(output)
    for name, pattern, fix in _NOTATION_FAULTS:
        hit = pattern.search(text)
        if hit is not None:
            return GuardrailResult.retry(
                f"Your answer uses an unsafe dose notation ({name}: '{hit.group(0).strip()}'). "
                f"This is on the ISMP Do Not Use list -- {fix}. Restate the dose."
            )
    return GuardrailResult.allow()


# -------------------------------------------------------- patient identifiers

_NHS_NUMBER = re.compile(r"(?<!\d)(\d{3})[ -]?(\d{3})[ -]?(\d{4})(?!\d)")


def _is_nhs_number(digits: str) -> bool:
    """NHS number Modulus 11 check.

    Weight digits 1-9 by 10..2, sum, take 11 minus (sum mod 11). 11 means a check digit
    of 0; 10 means the number is invalid and never issued. Validating properly matters:
    a ten-digit lab accession or a bare 2,000,000,000 would otherwise be redacted as an
    identifier, and a guard that cries wolf on clinical data gets switched off.
    """
    if len(digits) != 10 or not digits.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(digits[:9], range(10, 1, -1)))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(digits[9])


def _find_nhs_number(text: str) -> str | None:
    for match in _NHS_NUMBER.finditer(text):
        digits = "".join(match.groups())
        if _is_nhs_number(digits):
            return match.group(0)
    return None


# Identifiers that travel with a patient. The harness's own detector covers emails,
# cards and national insurance/SSN shapes but NOT UK phone numbers or NHS numbers, so
# those are added here rather than assumed.
# `(?<!\d)`/`(?!\d)` are load-bearing: without a left digit boundary this pattern finds
# a "phone number" inside any long run of digits, so a ten-digit lab accession or a
# plain 2000000000 was being withheld as patient data.
_UK_PHONE = re.compile(
    r"(?<!\d)(?:\+44[\s.-]?\(?0\)?|\+44|0)[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)"
)
# Case-sensitive on purpose. Under `re.I` the inward code `\d[A-Z]{2}` matches a dose:
# "Vitamin B12 2mg" parses as outward "B12" + inward "2mg", so every B12 prescription
# was withheld as a postcode. Postcodes are conventionally written uppercase, and the
# unit exclusion catches the remaining collisions ("B12 2MG").
_UK_POSTCODE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{1,2}\d[A-Z\d]?[ ]?\d(?!(?:MG|ML|KG|IU|MU)(?![A-Z]))[A-Z]{2}"
    r"(?![A-Za-z0-9])"
)
_DOB = re.compile(
    r"(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})(?!\d)"
)
_MRN = re.compile(r"(?<![A-Za-z0-9])(?:MRN|hospital number|patient (?:id|number))\s*:?\s*\w+", re.I)

# Built once, at import, because compiling the pattern set per call would put it on the
# hot path of every guarded answer. Its own verdict is `replace` -- it redacts what it
# finds -- and that is read purely as a signal that it matched something.
_PII = detectors.personal_data()


def no_patient_identifiers(output: object) -> GuardrailResult:
    """No patient-identifiable data leaves, however correct the dose was.

    This one blocks rather than redacting or retrying. Redaction would return a mangled
    answer as if it were the real one, and retrying asks the model that just disclosed
    to have another go -- neither is containment, and under UK GDPR a disclosure has
    already happened by the time you are deciding what to do about it.

    Checked in order of specificity so the block message names the actual identifier: a
    clinician reading "blocked: NHS number" can act on it, where "blocked: personal
    data" only prompts a second look at an answer they are no longer allowed to see.
    """
    text = _text(output)

    # The message names the KIND of identifier and never the value. Quoting it would
    # copy the identifier into the block reason, the event, the receipt and the trace --
    # withholding an answer while reproducing the data in the audit trail is not
    # containment, it just moves the disclosure somewhere less obvious.
    if _find_nhs_number(text):
        return GuardrailResult.block(
            "The answer contained what validates as an NHS number and was withheld."
        )
    for label, pattern in (
        ("a UK phone number", _UK_PHONE),
        ("a hospital/MRN number", _MRN),
        ("a date of birth", _DOB),
        ("a UK postcode", _UK_POSTCODE),
    ):
        if pattern.search(text) is not None:
            return GuardrailResult.block(
                f"The answer contained {label} and was withheld."
            )
    if _PII(text).action == "replace":
        return GuardrailResult.block(
            "The answer contained personal data and was withheld."
        )
    return GuardrailResult.allow()


# ------------------------------------------------------------------ topic scope

# A generous clinical vocabulary. Generous on purpose: this guard refuses to answer,
# so a false positive turns a legitimate clinical question away, which is a worse
# failure here than letting an odd off-topic question through. Anatomy, symptoms,
# drugs, settings, roles, measurements and the act of prescribing are all in scope.
_HEALTH_TERMS = (
    # care, people, places
    "patient", "clinic", "clinical", "hospital", "ward", "gp", "doctor", "nurse",
    "pharmacist", "pharmacy", "prescriber", "surgery", "icu", "a&e", "triage",
    "discharge", "admission", "referral", "consultant", "midwife", "paramedic",
    # medicines and dosing
    "dose", "dosage", "dosing", "drug", "medicine", "medication", "prescribe",
    "prescribed", "prescription", "tablet", "capsule", "injection", "infusion",
    "infuse", "iv", "oral", "mg/kg", "mcg/kg", "mg", "mcg", "ml", "mls",
    "millilitre", "millilitres", "litre", "litres", "microgram", "micrograms",
    "milligram", "milligrams", "formulary", "bnf", "administer", "titrate", "bolus",
    "sachet", "suspension", "vial", "ampoule", "syringe", "pill", "antibiotic",
    "analgesic", "anaesthetic", "vaccine", "vaccination", "immunisation",
    # named high-alert and common drugs
    "insulin", "heparin", "warfarin", "morphine", "opioid", "fentanyl", "oxycodone",
    "methotrexate", "chemotherapy", "paracetamol", "ibuprofen", "amoxicillin",
    "gentamicin", "vancomycin", "digoxin", "dopamine", "adrenaline", "penicillin",
    # physiology, anatomy, conditions
    "blood", "heart", "cardiac", "renal", "kidney", "liver", "hepatic", "lung",
    "respiratory", "neuro", "sepsis", "infection", "diabetes", "diabetic", "asthma",
    "cancer", "tumour", "fracture", "wound", "pain", "fever", "symptom", "diagnosis",
    "diagnose", "treatment", "therapy", "surgical", "operation", "anaemia",
    "hypertension", "glucose", "creatinine", "egfr", "bmi", "weight", "body weight",
    # measurement and monitoring
    "observation", "vital signs", "blood pressure", "heart rate", "temperature",
    "oxygen", "saturation", "mmol", "mmhg", "bpm", "reference range", "normal range",
    "health", "healthcare", "medical", "nhs", "care plan", "safeguarding",
    # nutrients and elements that show up in reference questions
    "vitamin", "ascorbic", "potassium", "sodium", "calcium", "magnesium", "iron",
    "electrolyte", "carbohydrate", "protein", "fluid",
    # hospital operations. In scope because they are the work of a ward, but kept out
    # of triage's CLINICAL stakes list on purpose: sterilising trays and counting stock
    # are hospital tasks where being wrong harms nobody, and that is the whole hard/LOW
    # quadrant. Scope and stakes are different questions and must not share a lexicon.
    "ward round", "ward", "shift", "rota", "handwash", "ppe", "glove", "gloves",
    "mask", "masks", "apron", "autoclave", "sterilise", "sterile", "swab", "specimen",
    "culture", "petri", "theatre", "stockroom", "stock", "supplies", "trolley", "bed",
    "bay", "staff", "blister pack", "pack", "course", "dispensary", "storeroom",
)

# Named off-topic domains. Only used to make the refusal specific -- the decision to
# refuse is made by the absence of any health term, not by this list.
_OFF_TOPIC = (
    ("sport", ("football", "premier league", "cricket", "tennis", "olympics", "world cup")),
    ("politics", ("election", "prime minister", "parliament", "president", "political party")),
    ("travel", ("flight", "holiday", "hotel", "book a trip", "visa application")),
    ("cooking", ("recipe", "bake a", "cook a", "ingredients for")),
    ("entertainment", ("film", "movie", "netflix", "song lyrics", "video game")),
    ("personal finance", ("mortgage", "stock market", "cryptocurrency", "bitcoin", "tax return")),
)


# Whole-token matching, not substring. A plain `in` test reads "iv" out of "give",
# "iron" out of "environment" and "pack" out of "packaged", so "give me a recipe for
# lasagne" counted as a clinical question. Boundaries are non-word lookarounds rather
# than `\b` so multi-token terms like "mg/kg" and "a&e" still anchor correctly.
_HEALTH_RE = re.compile(
    "|".join(rf"(?<!\w){re.escape(t)}(?!\w)" for t in _HEALTH_TERMS), re.I
)


def health_topics_only(prompt: object) -> GuardrailResult:
    """Refuse anything that is not a health question. Runs on the PROMPT, not the answer.

    Scope is an input concern. Checking it on the way out means the model has already
    been paid for, the off-topic answer already exists, and the only thing left to do
    is throw it away -- so this is the one guard in the registry that runs before any
    compute is committed, and a refusal costs zero tokens.

    The test is "does this mention anything clinical at all", which is deliberately
    weak in the permissive direction: turning away a real clinical question is a worse
    outcome than answering an odd one, so the vocabulary is broad and the burden is on
    the prompt to contain nothing health-related whatsoever.
    """
    text = " ".join(_text(prompt).lower().split())
    if _HEALTH_RE.search(text):
        return GuardrailResult.allow()

    named = next((label for label, terms in _OFF_TOPIC if any(t in text for t in terms)), None)
    subject = f" This looks like a question about {named}." if named else ""
    return GuardrailResult.block(
        "This assistant answers clinical and medication questions only." + subject
        + " Ask about a dose, a medicine, a patient calculation or a clinical reference."
    )


def shows_working(output: object) -> GuardrailResult:
    """A deep-budget answer that shows no derivation did not use the compute it was given."""
    text = _text(output).strip()
    if len(text.splitlines()) > 1 or re.search(r"[×x*/+=]|\bper\b", text):
        return GuardrailResult.allow()
    return GuardrailResult.retry(
        "This task was allocated deep reasoning. Show the derivation, then give the "
        "final answer on its own last line."
    )


@dataclass(frozen=True)
class GuardSpec:
    name: str
    guard: Guard
    outcome: str            # what a failure does: "retry" or "block"
    description: str        # shown in Mission Control's rule editor
    stage: str = "output"   # "output" runs on the answer; "input" runs on the prompt

    @property
    def on_input(self) -> bool:
        return self.stage == "input"


REGISTRY: tuple[GuardSpec, ...] = (
    GuardSpec(
        "numeric_answer_present", numeric_answer_present, "retry",
        "The answer must contain a figure. A dose question answered in prose is re-asked.",
    ),
    GuardSpec(
        "units_present", units_present, "retry",
        "A stated dose must carry its unit. '270' is re-asked; '270 mg' passes.",
    ),
    GuardSpec(
        "no_hedging", no_hedging, "retry",
        "Rejects 'roughly', 'approximately', 'I think'. A dose is not an estimate.",
    ),
    GuardSpec(
        "safe_dose_notation", safe_dose_notation, "retry",
        "ISMP Do Not Use list: no trailing zero ('1.0 mg'), no naked decimal ('.5 mg'), "
        "no 'U' for units, no 'IU', no 'µg'. Each is a documented tenfold-error mechanism.",
    ),
    GuardSpec(
        "no_patient_identifiers", no_patient_identifiers, "block",
        "Withholds the answer entirely if it carries an NHS number (Modulus 11 checked), "
        "phone, MRN, date of birth, postcode or email.",
    ),
    GuardSpec(
        "shows_working", shows_working, "retry",
        "A deep-budget answer must show its derivation, not just assert a dose.",
    ),
    GuardSpec(
        "health_topics_only", health_topics_only, "block",
        "Refuses anything that is not a clinical question. Runs on the prompt, so an "
        "off-topic request is turned away before any compute is committed.",
        stage="input",
    ),
)

_BY_NAME = {spec.name: spec for spec in REGISTRY}


def catalogue() -> list[dict]:
    """What the rule editor offers in its guardrail picker."""
    return [
        {"name": s.name, "outcome": s.outcome, "description": s.description, "stage": s.stage}
        for s in REGISTRY
    ]


# ------------------------------------------------------------------ layer 1: per call


def input_chain(names: tuple[str, ...] = ()) -> InputGuardrail:
    """Redaction (always on) plus whichever input-stage guards the rule asked for.

    Redaction runs first, because the framework feeds each guard the text the previous
    one left behind -- so the cleaned prompt is what the scope check inspects, what
    reaches the model, and what lands in the message history. Secrets and personal data
    in a prompt are not a domain concern: there is no rule you should have to write to
    stop leaking an API key to a model endpoint.

    The scope guard is enforced by the framework, not by us. `InputGuardrail` turns a
    `block` verdict into `SkipModelRequest`, so an off-topic prompt never reaches the
    model at all and costs nothing, and the harness emits its own `trace_block` span --
    a refusal is visible in Logfire next to the calls it did not make. Note the
    framework also rejects `retry()` from an input guard outright, which is why
    `health_topics_only` is declared `block`.

    Note the limit, and do not mistake this for the boundary control: this redacts on
    the way out of *our* process. The harness detector does not recognise NHS numbers or
    UK phone numbers, and a prompt that never enters this process is never seen here at
    all. Stopping patient data at the edge is the Gateway protection's job.
    """
    guards: list = [detectors.redact_secrets, detectors.redact_personal_data]
    guards += [
        _BY_NAME[n].guard for n in names if n in _BY_NAME and _BY_NAME[n].on_input
    ]
    return InputGuardrail(guard=guards)


def output_chain(names: tuple[str, ...]) -> OutputGuardrail | None:
    """The guards this task's rule asked for, in the order the rule listed them.

    Input-stage guards are filtered out: `health_topics_only` inspects the prompt, and
    running it against an answer would ask "does this reply mention anything clinical",
    which is a different and much worse question.
    """
    guards = [
        _BY_NAME[n].guard for n in names if n in _BY_NAME and not _BY_NAME[n].on_input
    ]
    return OutputGuardrail(guard=guards) if guards else None


def capabilities(names: tuple[str, ...] = ()) -> list:
    """The `capabilities=[...]` list for a worker Agent under this rule."""
    caps: list = [input_chain(names)]
    if chain := output_chain(names):
        caps.append(chain)
    return caps


def check_input(names: tuple[str, ...], prompt: str) -> Report:
    """Run the rule's input-stage guards over the prompt, before any compute is committed.

    The mirror of `check()`, and there for the same reason the output gate exists: the
    per-call `InputGuardrail` only protects calls that are actually made, so it cannot
    speak for the stub worker or for a `sampler` someone else supplied. Running the same
    guard here means scope is enforced once for the task, whatever the seam underneath
    is, and the loop can refuse before it fans out.
    """
    verdicts: list[Verdict] = []
    for name in names:
        spec = _BY_NAME.get(name)
        if spec is None or not spec.on_input:
            continue
        result = spec.guard(prompt)
        verdicts.append(
            Verdict(name=name, outcome=result.action, detail=result.message or "")
        )
    return Report(verdicts=verdicts)


# ------------------------------------------------------- layer 2: aggregated answer


@dataclass
class Verdict:
    name: str
    outcome: str            # "allow" | "retry" | "block"
    detail: str = ""

    def to_json(self) -> dict:
        return {"name": self.name, "outcome": self.outcome, "detail": self.detail}


@dataclass
class Report:
    verdicts: list[Verdict]

    @property
    def blocked(self) -> bool:
        return any(v.outcome == "block" for v in self.verdicts)

    @property
    def failed(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.outcome != "allow"]

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def block_message(self) -> str:
        return next((v.detail for v in self.verdicts if v.outcome == "block"), "")


def check(names: tuple[str, ...], answer: str) -> Report:
    """Run the rule's guards over the answer best-of-N settled on.

    Pure and synchronous: no model call, no network. `loop.py` uses the report to decide
    whether the answer stands, whether the task should be re-run with more compute, or
    whether it must be withheld.
    """
    verdicts: list[Verdict] = []
    for name in names:
        spec = _BY_NAME.get(name)
        if spec is None or spec.on_input:
            continue    # input-stage guards already ran, on the prompt, before spending
        result = spec.guard(answer)
        # `action` is the guard's own verdict -- read it rather than inferring one from
        # the presence of a message, so a guard that blocks without explaining itself
        # still blocks.
        verdicts.append(
            Verdict(name=name, outcome=result.action, detail=result.message or "")
        )
    return Report(verdicts=verdicts)
