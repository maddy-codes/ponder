"""Guardrails: the rule says which checks an answer must clear, and a trip buys compute."""

import asyncio
import json

import pytest

from agent.budget import decide
from agent.events import Emitter
from agent.guardrails import (
    capabilities,
    catalogue,
    check,
    check_input,
    health_topics_only,
)
from agent.loop import run_task
from agent.rules import apply, load_rules
from agent.tasks import Task
from agent.triage import heuristic_triage


class Quiet(Emitter):
    """Collects events instead of writing them anywhere."""

    def __init__(self) -> None:
        self.events = []

    def emit(self, event):
        event.roll_up()
        self.events.append(event)
        return event

    def progress(self, event) -> None:
        pass


# ----------------------------------------------------------------- the guards


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("The dose is 270 mg.", []),            # trailing full stop must not fail the unit
        ("270 mg", []),
        ("270", ["units_present"]),
        # units_present stays quiet when there is no quantity at all: the missing
        # number is already numeric_answer_present's complaint, and two guards
        # reporting one fault reads as two faults.
        ("no figure at all", ["numeric_answer_present"]),
        ("roughly 270 mg", ["no_hedging"]),
        ("I think it is 270 mg", ["no_hedging"]),
    ],
)
def test_guards_rule_on_the_answer(answer, expected):
    names = ("numeric_answer_present", "units_present", "no_hedging")
    assert [v.name for v in check(names, answer).failed] == expected


def test_units_guard_does_not_fire_inside_a_word():
    """'them' must not read as the unit 'm', or every prose answer escalates."""
    assert check(("units_present",), "them all, 5 kg").ok


def test_patient_identifiers_block_rather_than_retry():
    report = check(("no_patient_identifiers",), "Contact jane.doe@nhs.net about the dose")
    assert report.blocked
    assert not check(("no_patient_identifiers",), "The dose is 270 mg").blocked


def test_unknown_guard_name_is_ignored_not_fatal():
    """A rule authored in the UI can name a guard a later build removed."""
    assert check(("no_such_guard", "numeric_answer_present"), "42").verdicts[0].name == (
        "numeric_answer_present"
    )


def test_every_catalogued_output_guard_is_runnable():
    for spec in catalogue():
        if spec["stage"] == "input":
            continue    # runs on the prompt; check() is the answer-side gate
        assert check((spec["name"],), "42 mg").verdicts, spec["name"]


def test_capabilities_always_include_the_input_chain():
    """Secret and PII redaction is not a domain concern -- no rule should be needed."""
    assert len(capabilities(())) == 1
    assert len(capabilities(("no_hedging",))) == 2


# ----------------------------------------------- the rule carries the guardrails


def test_rule_selects_the_guardrails():
    prompt = "A paediatric patient weighs 18 kg. The dose is 15 mg/kg."
    scores = heuristic_triage(prompt)
    final = apply(prompt, decide(scores.difficulty, scores.stakes))
    assert final.matched_rule == "paediatric_dose"
    assert "units_present" in final.guardrails
    assert "safe_dose_notation" in final.guardrails


def test_unpoliced_tasks_get_scope_but_no_domain_guardrails():
    """No clinical rule claims a rota sum, so none of the dose guards apply -- but
    policy-level scope still does."""
    prompt = "A ward rota covers 3 days. How many hours is that?"
    scores = heuristic_triage(prompt)
    guards = apply(prompt, decide(scores.difficulty, scores.stakes)).guardrails
    assert guards == ("health_topics_only",)


# ------------------------------------------------------ a trip buys more compute


def test_guardrail_trip_escalates_a_cheap_task(monkeypatch):
    """The move a compliance filter cannot make: spend more instead of refusing.

    The cheap pass answers without a unit, which the rule does not accept, so the
    budget is escalated to deep and the fan-out is re-run.
    """
    import agent.loop as loop

    calls: list[tuple[str, int]] = []

    async def sampler(task, budget, rule_id, n, guardrails):
        from agent.worker import WorkerResult

        calls.append((budget, n))
        text = "36" if budget == "cheap" else "36 kg"
        return [WorkerResult(text, 10, 0.1) for _ in range(n)]

    task = Task(
        id="grd", prompt="Ballpark stock weight: 12 boxes of gloves at 3 kg each, rough total?", answer="36 kg",
        kind="numeric",
    )
    emitter = Quiet()
    event = asyncio.run(run_task(task, "ponder", emitter, sampler=sampler))

    assert event.matched_rule == "ward_estimate"
    assert calls[0][0] == "cheap", "it must genuinely try cheap first"
    assert len(calls) == 2, "the trip must buy a second, wider pass"
    assert calls[1][0] == "deep"
    assert event.guardrail_escalated
    assert event.budget == "deep"
    assert "escalated to deep" in (event.rule_reason or "")
    assert [v.outcome for v in event.guardrail_verdicts] == ["allow", "allow"]


def test_escalation_happens_at_most_once(monkeypatch):
    """A guard that can never be satisfied must not loop the budget upward forever."""
    async def sampler(task, budget, rule_id, n, guardrails):
        from agent.worker import WorkerResult

        return [WorkerResult("36", 10, 0.1) for _ in range(n)]

    task = Task(
        id="grd2", prompt="Ballpark stock weight: 12 boxes of gloves at 3 kg each, rough total?", answer="36 kg",
        kind="numeric",
    )
    event = asyncio.run(run_task(task, "ponder", Quiet(), sampler=sampler))
    assert event.guardrail_escalated
    assert "units_present" in event.guardrails_failed, "the failure stays on the record"


def test_blocked_answer_is_withheld_not_returned():
    async def sampler(task, budget, rule_id, n, guardrails):
        from agent.worker import WorkerResult

        return [WorkerResult("Pay jane.doe@acme.com 1234.56", 10, 0.1) for _ in range(n)]

    task = Task(
        id="grd3", prompt="What is the gross total of invoice 4471 at 1029.00 plus VAT?",
        answer="1234.80", kind="numeric",
    )
    event = asyncio.run(run_task(task, "ponder", Quiet(), sampler=sampler))
    assert event.guardrail_blocked
    assert "jane.doe@acme.com" not in (event.answer or "")
    assert (event.answer or "").startswith("[withheld by guardrail]")


def test_baselines_never_see_guardrails():
    """A baseline that consulted the policy would stop being a baseline."""
    from agent.loop import plan

    task = Task(id="b1", prompt="dose 15 mg/kg for 18 kg", answer="270", kind="numeric")
    for strategy in ("cheap", "deep"):
        _, decision = plan(task, strategy)
        assert decision.guardrails == ()
        assert decision.matched_rule is None


# =====================================================================================
# Per-guardrail matrix
#
# One section per entry in REGISTRY. Each covers three things, because a guard has three
# ways to be wrong and only one of them is "fails to fire":
#
#   passes   -- an answer the guard must let through
#   trips    -- the fault the guard exists to catch
#   boundary -- the near-miss on either side. A guard that fires on a good answer is not
#               merely noisy here: under `routine_estimate` it escalates the budget, so a
#               false positive spends the deep fan-out for nothing. That is the expensive
#               direction, so it is the direction tested hardest.
# =====================================================================================


def _outcome(name: str, answer: str) -> str:
    """The single verdict `name` returns for `answer`."""
    return check((name,), answer).verdicts[0].outcome


# ------------------------------------------------------ 1. numeric_answer_present


@pytest.mark.parametrize(
    "answer",
    [
        "42",
        "0",                    # zero is an answer, not an absence
        "-5",                   # negative
        "1,234.56",             # thousands separator and decimal
        ".5",                   # leading-dot decimal
        "The total is 1234.80 including VAT.",
        "Order #4471 shipped",  # a figure anywhere counts
    ],
)
def test_numeric_answer_present_allows_any_figure(answer):
    assert _outcome("numeric_answer_present", answer) == "allow"


@pytest.mark.parametrize(
    "answer",
    [
        "no digits here",
        "The answer is three",   # spelled out is not a figure
        "",
        "I could not compute it.",
    ],
)
def test_numeric_answer_present_trips_on_prose(answer):
    assert _outcome("numeric_answer_present", answer) == "retry"


def test_numeric_answer_present_retries_rather_than_blocks():
    """Outcome, not just failure: a missing figure is re-asked, never withheld."""
    assert not check(("numeric_answer_present",), "prose only").blocked


# ----------------------------------------------------------------- 2. units_present


@pytest.mark.parametrize(
    "answer",
    [
        "270 mg",
        "The dose is 270 mg.",   # trailing full stop must not eat the unit
        "5 kg",
        "30 min",
        "37 °C",
        "5 m/s",
        "3 tablets",
        "250 ms",
    ],
)
def test_units_present_allows_a_quantity_with_its_unit(answer):
    assert _outcome("units_present", answer) == "allow"


@pytest.mark.parametrize(
    "answer",
    [
        "270mg",                 # unit flush against the figure is ordinary notation
        "250ms",
        "50%",                   # a percentage is *always* written against its figure
        "a 12% VAT rate",
        "Fuel reserve is 8% above minimum.",
        "The safety factor is 1.5, giving a 20% margin.",
    ],
)
def test_units_present_accepts_a_unit_flush_against_its_figure(answer):
    """The expensive false positive.

    `(?<!\\w)` before the unit rejected every one of these, because the character before
    the unit is the figure's own last digit. Under a rule carrying this guard that meant
    a correct answer bought a deep re-run; `%` in particular could never match at all.
    """
    assert _outcome("units_present", answer) == "allow"


@pytest.mark.parametrize("answer", ["270", "The total is 36", "1,234.56"])
def test_units_present_trips_on_a_bare_quantity(answer):
    assert _outcome("units_present", answer) == "retry"


@pytest.mark.parametrize(
    "answer",
    [
        "them all, 5 kg",        # 'm' inside 'them'
        "the minimum is 5 kg",   # 'min' inside 'minimum'
        "5 kg of information",   # 'in' inside 'information'
        "2 days, no format",     # 'f' inside 'format'
    ],
)
def test_units_present_does_not_read_a_unit_out_of_a_word(answer):
    """A unit must be a whole token, or ordinary prose satisfies the guard by accident."""
    assert _outcome("units_present", answer) == "allow"


def test_units_present_is_silent_when_there_is_no_quantity():
    """The missing figure is numeric_answer_present's complaint; two guards reporting
    one fault reads as two faults."""
    assert _outcome("units_present", "no figure at all") == "allow"


# -------------------------------------------------------------------- 3. no_hedging


@pytest.mark.parametrize(
    "answer",
    [
        "roughly 270 mg",
        "approximately 270 mg",
        "I think it is 270 mg",
        "I believe the total is 1234.80",
        "probably 270",
        "It may be about 5 kg",
        "The load might be 12 kN",
        "I'm not sure, but 270 mg",
        "unsure",
        "This cannot be certain at 270 mg",
    ],
)
def test_no_hedging_trips_on_an_uncommitted_answer(answer):
    assert _outcome("no_hedging", answer) == "retry"


@pytest.mark.parametrize(
    "answer",
    [
        "270 mg",
        "The dose is exactly 270 mg.",
        "The approximation theorem gives 270 mg",  # 'approx' inside a longer word
        "Round to 270 mg",
        "The rough surface is 5 mm",               # 'rough' is not 'roughly'
    ],
)
def test_no_hedging_allows_a_committed_answer(answer):
    assert _outcome("no_hedging", answer) == "allow"


def test_no_hedging_names_the_phrase_it_caught():
    """The retry message has to tell the model what to remove, not just that it failed."""
    detail = check(("no_hedging",), "roughly 270 mg").failed[0].detail
    assert "roughly" in detail


# ------------------------------------------------------------- 4. no_personal_data


@pytest.mark.parametrize(
    "answer",
    [
        "NHS number 943 476 5919",              # valid Modulus 11
        "nhs 9434765919",
        "Contact the patient on 07700 900123",
        "tel +44 7911 123456",
        "DOB 12/03/1981",
        "born 1981-03-12",
        "MRN: A48219",
        "Address SW1A 1AA",
        "email jane.doe@nhs.net",
    ],
)
def test_no_patient_identifiers_blocks_a_leak(answer):
    report = check(("no_patient_identifiers",), answer)
    assert report.blocked
    assert report.block_message, "a block must explain itself"


@pytest.mark.parametrize(
    "answer",
    [
        "The dose is 270 mg",
        "Vitamin B12 2mg daily",                # 'B12 2mg' is not a postcode
        "Lab accession 1234567890 pending",     # ten digits, fails Modulus 11
        "Sample 2000000000",
        "Serum sodium 139 mmol/L",
        "Give 2 tablets at 0800 and 2000",
        "Run the infusion at 125 ml/hour",
    ],
)
def test_no_patient_identifiers_allows_clinical_text(answer):
    assert _outcome("no_patient_identifiers", answer) == "allow"


def test_an_nhs_number_is_checksum_validated_not_just_ten_digits():
    """Without Modulus 11 every ten-digit lab value is withheld as an identifier."""
    assert _outcome("no_patient_identifiers", "ref 9434765919") == "block"   # valid
    assert _outcome("no_patient_identifiers", "ref 9434765918") == "allow"   # bad digit


def test_the_block_message_never_repeats_the_identifier():
    """Withholding the answer while copying the identifier into the reason, the event,
    the receipt and the trace is not containment."""
    for leak in ("943 476 5919", "07700 900123", "SW1A 1AA"):
        message = check(("no_patient_identifiers",), f"contact {leak}").block_message
        assert leak not in message, message
        assert message, "it must still say something actionable"


def test_blocking_guards_are_the_ones_that_cannot_be_walked_back():
    """Every other guard buys compute. These two contain."""
    blocking = {s["name"] for s in catalogue() if s["outcome"] == "block"}
    assert blocking == {"no_patient_identifiers", "health_topics_only"}


# ------------------------------------------------------------------ 5. shows_working


@pytest.mark.parametrize(
    "answer",
    [
        "18 kg x 15 = 270 mg",       # arithmetic operator
        "18 × 15 = 270",
        "1029.00 * 1.2 = 1234.80",
        "15 mg per kg of body weight",   # 'per' reads as a derivation
        "total = 270",
        "step one\nstep two",            # more than one line is working shown
    ],
)
def test_shows_working_allows_a_derivation(answer):
    assert _outcome("shows_working", answer) == "allow"


@pytest.mark.parametrize("answer", ["270", "270 mg", "  270  ", "The answer is 270 mg"])
def test_shows_working_trips_on_a_bare_assertion(answer):
    """Deep compute that produced one asserted line did not use what it was given."""
    assert _outcome("shows_working", answer) == "retry"


def test_shows_working_ignores_surrounding_whitespace():
    """A trailing newline must not read as a second line of working."""
    assert _outcome("shows_working", "270 mg\n") == "retry"


# --------------------------------------------------------- shared across the registry


def test_a_typed_output_is_inspected_by_its_fields_not_its_repr():
    """`OutputGuardrail` hands over the model instance; `str(model)` would hide the
    field contents from every regex above."""
    from pydantic import BaseModel

    class Answer(BaseModel):
        value: str

    assert _outcome("numeric_answer_present", Answer(value="270 mg")) == "allow"
    assert _outcome("units_present", Answer(value="270")) == "retry"
    assert _outcome("no_patient_identifiers", Answer(value="jane.doe@nhs.net")) == "block"


def test_every_registered_guard_reports_under_its_own_name():
    """`check` keys verdicts by name, and the rule editor and TaskEvent both read them."""
    for spec in catalogue():
        runner = check_input if spec["stage"] == "input" else check
        verdict = runner((spec["name"],), "270").verdicts[0]
        assert verdict.name == spec["name"]
        assert verdict.outcome in {"allow", "retry", "block"}


def test_guards_run_in_the_order_the_rule_listed_them():
    """`rule_reason` and the receipt render verdicts in order, so order is contractual."""
    names = ("no_hedging", "units_present", "numeric_answer_present")
    assert [v.name for v in check(names, "roughly 270").verdicts] == list(names)


def test_every_guard_in_rules_json_exists_in_the_registry():
    """A rule naming a guard the registry lost would silently stop being enforced:
    `output_chain` filters unknown names out without complaint."""
    import json as _json
    from pathlib import Path

    known = {s["name"] for s in catalogue()}
    policy = _json.loads(Path("agent/rules.json").read_text())
    for rule in policy["rules"]:
        for name in rule["then"].get("guardrails", []):
            assert name in known, f"{rule['name']} names unknown guard {name!r}"


# =====================================================================================
# safe_dose_notation -- the ISMP Do Not Use list
# =====================================================================================


@pytest.mark.parametrize(
    "answer,fault",
    [
        ("Give 1.0 mg", "trailing zero"),        # read as 10 mg if the point is lost
        ("Give 2.0 mL", "trailing zero"),
        ("Give .5 mg", "naked decimal"),         # read as 5 mg
        ("Dose .25 mcg", "naked decimal"),
        ("Give 10U insulin", "U for units"),     # U read as a zero -> 100 units
        ("Give 10 u", "U for units"),
        ("5000 IU heparin", "IU"),
        ("Give 250 ug", "microgram symbol"),     # ug read as mg -> thousandfold
        ("Give 250 µg", "microgram symbol"),
        ("Take QD", "latin frequency"),
        ("Dose QOD", "latin frequency"),
    ],
)
def test_safe_dose_notation_catches_each_ismp_fault(answer, fault):
    verdict = check(("safe_dose_notation",), answer).failed[0]
    assert verdict.outcome == "retry"
    assert fault in verdict.detail, verdict.detail


@pytest.mark.parametrize(
    "answer",
    [
        "Give 1 mg",
        "Give 0.5 mg",
        "Give 10 units insulin",
        "5000 international units",
        "Give 250 mcg",
        "Take daily",
        "270 mg",
        "2.05 mg",              # the 0 is interior, not trailing
        "0.25 mg/kg",
        "Temperature 37.2 C",
        "Give 12 units",
    ],
)
def test_safe_dose_notation_allows_correctly_written_doses(answer):
    assert _outcome("safe_dose_notation", answer) == "allow"


def test_safe_dose_notation_can_fail_an_arithmetically_correct_answer():
    """The value is right and the notation is still a medication error. That is the
    point of the guard -- it checks how the dose is written, not what it equals."""
    assert _outcome("safe_dose_notation", "The dose is 1.0 mg") == "retry"
    assert _outcome("safe_dose_notation", "The dose is 1 mg") == "allow"


# =====================================================================================
# health_topics_only -- scope, enforced on the PROMPT
# =====================================================================================


@pytest.mark.parametrize(
    "prompt",
    [
        "Who won the World Cup in 2022?",
        "Give me a recipe for lasagne",
        "What is bitcoin worth?",
        "Who is the prime minister?",
        "Book me a flight to Rome",
        "Write me a poem about the sea",
        "What is 12 * 12?",
        "How do I fix my car?",
    ],
)
def test_health_topics_only_refuses_off_topic_prompts(prompt):
    report = check_input(("health_topics_only",), prompt)
    assert report.blocked
    assert "clinical" in report.block_message.lower()


@pytest.mark.parametrize(
    "prompt",
    [
        "A 24 kg child is prescribed 20 mg/kg. What is the dose?",
        "What is the normal range for serum sodium?",
        "What does the abbreviation BNF stand for?",
        "Which vitamin is also known as ascorbic acid?",
        "How many gloves are in a box of 12 packs?",      # ward operations count
        "A night shift lasts 4 hours. How many minutes?",
        "Convert 2.5 litres to millilitres.",
    ],
)
def test_health_topics_only_allows_clinical_and_ward_prompts(prompt):
    assert not check_input(("health_topics_only",), prompt).blocked


def test_scope_matches_whole_words_not_substrings():
    """A plain `in` test read 'iv' out of 'give' and 'iron' out of 'environment', so
    'give me a recipe' counted as clinical."""
    for prompt in ("Give me a recipe for lasagne", "Tell me about the environment",
                   "Describe my bedroom", "How is the packaging recycled?"):
        assert check_input(("health_topics_only",), prompt).blocked, prompt


def test_scope_names_the_off_topic_subject_when_it_recognises_one():
    assert "sport" in check_input(("health_topics_only",), "Who won the World Cup?").block_message


def test_scope_is_an_input_guard_and_never_runs_on_the_answer():
    """Asking 'does this reply mention anything clinical' is a different and much worse
    question than asking it of the prompt."""
    assert check(("health_topics_only",), "anything at all").verdicts == []
    assert check_input(("health_topics_only",), "anything at all").verdicts


def test_scope_applies_to_every_task_even_with_no_matching_rule():
    """An off-topic prompt matches no clinical rule by definition, so scope cannot be
    expressed as one -- it is declared once for the policy."""
    from agent.rules import scope_guardrails

    assert "health_topics_only" in scope_guardrails()
    final = apply("Who won the World Cup?", decide(0.2, 0.2))
    assert final.matched_rule is None
    assert "health_topics_only" in final.guardrails


# ------------------------------------------------- enforced by Pydantic, not by us


def test_pydantic_skips_the_model_call_entirely_for_an_off_topic_prompt():
    """The framework enforces scope, we only declare it.

    `InputGuardrail` turns a `block` verdict into `SkipModelRequest`, so the request is
    never issued and the refusal costs nothing. Asserting on the call count rather than
    the text is the point: a guard that merely rewrote the answer would pass a string
    check while still having paid for the tokens.
    """
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    calls: list = []

    def record(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[TextPart(content="MODEL WAS CALLED")])

    agent = Agent(FunctionModel(record), capabilities=capabilities(("health_topics_only",)))

    clinical = asyncio.run(agent.run("What is the dose for a 24 kg child at 20 mg/kg?"))
    assert len(calls) == 1 and str(clinical.output) == "MODEL WAS CALLED"

    calls.clear()
    refused = asyncio.run(agent.run("Who won the World Cup in 2022?"))
    assert calls == [], "the model must never be called for an off-topic prompt"
    assert "clinical" in str(refused.output).lower()


def test_the_scope_guard_is_attached_as_a_real_input_capability():
    """It must ride on InputGuardrail, not be hand-rolled -- otherwise none of the
    framework's skip-and-trace behaviour applies."""
    from pydantic_ai_harness.guardrails import InputGuardrail, OutputGuardrail

    caps = capabilities(("health_topics_only", "units_present"))
    inputs = [c for c in caps if isinstance(c, InputGuardrail)]
    outputs = [c for c in caps if isinstance(c, OutputGuardrail)]
    assert len(inputs) == 1 and len(outputs) == 1

    # the scope guard is in the INPUT chain, and not in the output one
    assert health_topics_only in list(inputs[0].guard)
    assert health_topics_only not in list(outputs[0].guard)


def test_a_blocked_prompt_costs_nothing_and_still_emits_one_event():
    """The refusal is the finished task: zero samples, zero tokens, one TaskEvent."""
    async def sampler(task, budget, rule_id, n, guardrails):
        raise AssertionError("the loop must not spend on an out-of-scope prompt")

    task = Task(id="scope1", prompt="Who won the World Cup in 2022?", answer="", kind="exact")
    emitter = Quiet()
    event = asyncio.run(run_task(task, "ponder", emitter, sampler=sampler))

    assert event.guardrail_blocked
    assert event.samples == [] and event.total_tokens == 0
    assert event.status == "done"
    assert len(emitter.events) == 1, "still exactly one durable TaskEvent"
    assert event.correct is None, "a refusal is not a wrong answer"
