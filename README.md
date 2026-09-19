# Ponder — the layer between a domain rule and how hard the model thinks

> Reasoning-effort control already exists as a provider API parameter — OpenAI ships
> `reasoning_effort`, Anthropic ships `budget_tokens`, Gemini ships `thinkingLevel`.
> Domain compliance and verification systems already exist too. **Neither connects a named
> domain rule to how much the model reasons and verifies before its answer is trusted.**
> Ponder is that connective layer: write a rule once — *"financial totals always get
> verified"* — and it governs effort and verification automatically, auditable through
> Logfire, without touching the model or the prompt.

Underneath that layer, Ponder scores every task on **difficulty × stakes** and allocates
compute accordingly. Trivial items get one cheap call. Hard or high-stakes items get a
deep-reasoning rule, best-of-N sampling fanned out across Modal containers, and — when being
wrong is expensive — an answer that is **executed in a sandbox before it is trusted**. A
named rule outranks that score whenever one applies.

The result is not "more accurate". It is **the same accuracy where it matters, for half
the compute, with the remaining errors pushed onto tasks nobody is harmed by**.

## Using it

Ponder is designed as a drop-in replacement for a direct model call — same interface, plus an
effort decision and an audit trail.

```python
# before — your agent calls the model directly
answer = model.complete(prompt)

# after — same call shape, Ponder decides the effort
from agent.ask import ponder

result = ponder(prompt)
# result.answer        — the response
# result.matched_rule  — which domain rule fired, if any ("paediatric_dose")
# result.rule_reason   — why that rule exists, and what it overrode
# result.budget        — "cheap" or "deep"
# result.verified      — True if a sandbox executed and confirmed it
# result.event         — the full TaskEvent, already in Logfire, Convex and events.jsonl
```

```bash
uv run python -m agent.ask "A child weighs 24 kg. Amoxicillin is 20 mg/kg per dose. What is a single dose in mg?"
```

### Governing an agent you already have

`ponder()` replaces a model call. `govern()` goes in front of an **agent someone else already
wrote** — its own model, its own tools, its own prompts — and polices every call it makes:

```python
from pydantic_ai import Agent
from agent.govern import govern

ward = Agent("openai:gpt-5", tools=[lookup_weight, check_allergies])   # unchanged
ward = govern(ward)                                                    # one line

result = ward.run_sync("A child weighs 24 kg. Amoxicillin is 20 mg/kg per dose — what is one dose?")
result.output                 # the answer, as before
result.ponder.matched_rule    # 'paediatric_dose'
result.ponder.budget          # 'deep'  — the rule overrode the easy-looking score
result.ponder.samples         # 6       — best-of-N across Modal containers
result.ponder.verified        # True    — recomputed in a sandbox before it was trusted
```

The wrapped agent is **not modified**. Guardrails ride on Pydantic AI's per-run
`capabilities` parameter and reasoning effort rides on `model_settings`, so a governed agent
is the same object it was — no subclass, no second definition to keep in sync. And there is no
second pipeline: `govern` supplies a *sampler* to the same `run_task` the batch queue runs, so
a governed call gets the same triage, the same rules, the same guardrail gate, the same
sandbox, and one `TaskEvent` to the same three sinks. It shows up in Mission Control next to
everything else, with the same decision receipt.

A cheap task still costs exactly one call. Only what the policy says is consequential pays for
width and verification:

```
$ uv run python examples/governed_agent.py

Q  What is the capital of France?
A  The capital of France is Paris.
   rule=casual_lookup  budget=cheap  samples=1  not verified
   348 tokens · 1.30s

Q  A paediatric patient weighs 18 kg and the dose is 15 mg/kg. What is the dose in mg?
A  The dose is 18 kg × 15 mg/kg = 270 mg.
   rule=clinical_dose  budget=deep  samples=8  verified
   guardrails=numeric_answer_present, units_present, no_hedging
   2820 tokens · 8.47s
```

Measured over a 40-task queue (`agent/tasks.jsonl`, `artifacts/frontier.json`):

| strategy | high-stakes accuracy | tokens | GPU-seconds | misses that were low-stakes |
|---|---|---|---|---|
| always-cheap | 67% | 2,317 | 32 | 65% |
| always-deep | 89% | 182,377 | 2,508 | 67% |
| **ponder** | **89%** | **62,618** | **869** | **83%** |

Ponder holds always-deep's high-stakes accuracy on **34% of the compute**, and 83% of the
errors it does make are on things like a lily-pad riddle. Triage in that run is the live
`gemini-3.6-flash` judge, scoring from the prompt text alone.

---

## The demo case

One command, one prompt, every load-bearing part of the system:

```bash
uv run python scripts/demo_case.py
```

```
Insulin is dosed at 1 unit per 10 g of carbohydrate. A meal contains 80 g of
carbohydrate. How many units are required? Give the answer to one decimal place.
```

**Why this prompt.** Insulin is an ISMP high-alert medication, so the named rule demands
deep reasoning and sandbox verification however trivial `80 / 10` looks. And asking for
"one decimal place" pushes the model into writing **8.0 units** — a trailing zero on an
insulin dose is the textbook tenfold-overdose mechanism, because `8.0` read without its
decimal point is `80`. The request itself induces the unsafe notation, and the guardrail
catches it. The instruction and the safety rule genuinely conflict, and the audit record
says so rather than quietly complying.

What it asserts, and what a judge sees:

```
PASS  budget is deep                     budget=deep
PASS  a named rule overrode the score    rule=high_alert_medication
PASS  easy task, maximum effort          difficulty=0.1 stakes=0.9
PASS  the rule added what the score cannot sandbox + 5 named guards
PASS  Modal fanned out                   8 samples
PASS  sandbox executed the answer        ran=True passed=True
PASS  a guardrail fired                  tripped=['safe_dose_notation']
PASS  scope guard cleared the prompt     health_topics_only=allow
PASS  every required guard has a verdict 5/5 recorded
PASS  the answer is arithmetically right expected 8 units
```

Every guardrail the rule required carries a verdict, including the input-stage scope
check that cleared the prompt before any compute was committed:

```
   health_topics_only         allow
   numeric_answer_present     allow
   units_present              allow
-> safe_dose_notation         retry   unsafe dose notation (trailing zero: '8.0') — ISMP Do Not Use
   no_hedging                 allow
```

The script prints a **Logfire trace link** for the run. In the trace you see the eight
parallel Modal samples, the Gateway rule each carried, the token counts, the sandbox
execution, and the guardrail spans the harness emitted. The same verdicts appear on the
**decision receipt** in Mission Control — open the task and press *Receipt*.

Difficulty 0.10, stakes 0.90: the task is genuinely easy and still gets maximum effort.
That is the thesis in one line — **stakes bought the compute, not difficulty**.

## Integrating with the Pydantic AI library

Ponder is not a wrapper that reimplements an agent framework. It is a policy layer that sits
on Pydantic AI's own extension points, which is why a governed agent stays the object you
wrote. Three surfaces, in increasing order of how much of your code stays yours.

### 1. `ponder(prompt)` — replace a model call

```python
from agent.ask import ponder

result = ponder("A child weighs 24 kg. Amoxicillin is 20 mg/kg per dose. What is one dose?")
```

Ponder builds the `Agent` for you, one per (Gateway rule, guardrail chain), and runs the full
loop. Use this when the model call is yours to own.

### 2. `govern(agent)` — police an agent someone else wrote

```python
from pydantic_ai import Agent
from agent.govern import govern

ward = govern(Agent("openai:gpt-5", tools=[lookup_weight]))
result = ward.run_sync("...")
result.ponder.matched_rule   # the policy decision, alongside the normal output
```

`govern` **never mutates the agent**. It supplies a *sampler* to the same `run_task` the batch
queue uses, so a governed call gets the same triage, rules, guardrail gate, sandbox and one
`TaskEvent`. There is no second pipeline to keep in sync.

### 3. `capabilities()` — take just the guardrails

```python
from pydantic_ai import Agent
from agent.guardrails import capabilities

agent = Agent(model, capabilities=capabilities(("health_topics_only", "safe_dose_notation")))
```

The guard chain is a plain list of Pydantic capabilities. Attach it at construction, or pass
it per run, and use none of the rest of Ponder.

### Which Pydantic AI primitives are used, and where

| Pydantic AI / Harness primitive | Where | What it does for us |
|---|---|---|
| `Agent(...)` | `worker._agent_for` | one agent per (Gateway rule, guard chain) |
| `providers.gateway.gateway_provider` | `worker._gateway_model` | BYOK route to the Modal endpoint |
| `models.openai.OpenAIChatModel` | `worker._gateway_model` | the wire protocol vLLM serves |
| `capabilities=[...]` | `worker._agent_for`, `govern` | attaches guardrails without subclassing |
| `guardrails.InputGuardrail` | `guardrails.input_chain` | redaction + scope, **before** the request |
| `guardrails.OutputGuardrail` | `guardrails.output_chain` | answer checks, raises real `ModelRetry` |
| `guardrails.detectors` | `guardrails.input_chain` | first-party secret / PII redaction |
| `GuardrailResult.allow/retry/block` | every guard | the verdict vocabulary |
| `exceptions.ModelRetry` | raised by the framework | a failed output check re-asks the model |
| `guardrails.OutputBlocked` | caught in `worker.gateway_sample` | a policy refusal, not a failed call |
| `model_settings=` | `worker.call_settings` | reasoning effort + the Gateway rule header |
| `logfire.instrument_pydantic_ai()` | `events.py` | every call traced, with tokens |

### The two things worth copying

**Guardrails ride on `capabilities`, not on a subclass.** That parameter accepts a per-run
value, which is the whole reason `govern()` can police an agent it did not construct — the
guards travel with the call instead of having to be baked into someone else's `Agent`.

**A blocking input guard means the model is never called.** `InputGuardrail` turns a `block`
verdict into `SkipModelRequest`, so an out-of-scope prompt costs zero tokens and the harness
emits its own `trace_block` span. This is framework behaviour, not ours — the test asserts the
model call count is exactly `0`:

```python
agent = Agent(FunctionModel(record), capabilities=capabilities(("health_topics_only",)))
asyncio.run(agent.run("Who won the World Cup in 2022?"))
assert calls == []        # tests/test_guardrails.py
```

One constraint the framework enforces and worth knowing before you write a guard: an
`InputGuardrail` guard may **not** return `GuardrailResult.retry()` — it raises `UserError`.
Retry applies to model output only, which is why scope guards are declared `block`.

## The rule layer

**The rules are data, not code.** They live in `agent/rules.json`; `agent/rules.py` only loads
and compiles them; and they are authored in Mission Control's **Policy** panel by whoever owns
the domain. The person who knows that a dose must be recomputed is rarely the person who can
ship a Python change — here they do not have to be. Saving a rule takes effect on the very next
task, with no restart and no deploy: the loader reloads on mtime.

Each rule matches on the prompt — the same text triage sees, never the held-out ground truth —
and states outright what the match buys, in three clauses:

| rule | budget | verify | guardrails the answer must clear |
|---|---|---|---|
| `clinical_dose` | deep | ✅ | `numeric_answer_present`, `units_present`, `no_hedging` |
| `safety_margin` | deep | ✅ | `numeric_answer_present`, `units_present`, `no_hedging` |
| `financial_total` | deep | ✅ | `numeric_answer_present`, `no_hedging`, `no_personal_data` |
| `routine_estimate` | **cheap** | — | `numeric_answer_present`, `units_present` |
| `casual_lookup` | cheap | — | — |

`routine_estimate` is the interesting one: it spends cheap **on purpose**, but still demands a
usable figure with its unit. If the cheap pass cannot produce one, the guardrail trips and the
task escalates to deep — spending is adaptive, not just predicted.

A matched rule **outranks** the numeric score. With no match, `budget = f(difficulty, stakes)`
decides exactly as before, so the rule layer is additive rather than a replacement. Escalating
rules are declared first, so a dose question phrased as a lookup still escalates.

Every `TaskEvent` records `matched_rule` and `rule_reason`, and the reason says what the score
alone would have spent when the two disagreed — which is the audit trail for *"the policy, not
the classifier, chose this"*:

```
What is the total cost of 3 items at 4.50 each?
  difficulty 0.22 · stakes 0.12   →  the score alone would have spent cheap
  rule financial_total             →  deep, 5 samples, executed verification
```

On the 40-task benchmark queue the rules and the score agree on every task, so the frontier
numbers below are unchanged by this layer. The disagreement is easiest to see by typing a task
into Mission Control yourself.

### Guardrails: a failed check buys compute, it does not just refuse

The third clause of a rule names the **guardrails** its answer must clear. These are first-party
Pydantic — `InputGuardrail`, `OutputGuardrail` and the `detectors` from
`pydantic_ai_harness.guardrails` — enforced at two points:

1. **Per model call.** The guards are attached to the agent through Pydantic AI's
   `capabilities` parameter, so the framework runs them on every request: secrets and personal
   data are redacted out of the prompt before it is sent, and a failed output check becomes a
   real `ModelRetry` that makes the model fix its own answer. Each firing is its own Logfire
   span, in the same trace as the tokens it cost.
2. **On the aggregated answer.** Best-of-N picks its winner *after* every per-call guard has
   returned, so no guard has seen the string the caller actually gets. `agent/guardrails.py`
   runs the same checks once more over it.

The second point is where Ponder differs from a compliance filter. A filter's only move on a
bad output is to refuse. Ponder has another one: **a guardrail trip is evidence the task was
underfunded.** A cheap answer that trips a guard escalates to deep and re-runs, and
`TaskEvent.guardrail_escalated` records that it did.

```
Ballpark: 12 boxes at 3 kg each, rough total?
  rule routine_estimate     →  cheap, 1 sample
  answer "36"               →  guardrail units_present tripped
  ESCALATED                 →  deep, 5 samples
  answer "36 kg"            →  all guards pass
```

That is the move a difficulty router cannot make: having concluded the task was easy, it has
nothing left to spend. Escalation fires at most once and only upward from cheap — a deep answer
that still trips a guard keeps its verdicts on the record and stands, because every one of its
samples already had a framework-level retry, and re-running the widest budget on every failed
check would burn the compute this project exists to save. A `no_personal_data` trip is the one
exception: it blocks outright, because asking the model that just leaked to try again is not
containment.

Available guards are listed by `uv run python -m agent.rules --json`, and the editor offers
exactly those — a rule can never name a check the agent cannot run.

### Above the provider's own effort control, not beside it

The deep path sets **both** actuators: our Gateway rule *and* — where the served model exposes
one — the model's own reasoning parameter (`reasoning_effort`, and vLLM's `enable_thinking`
chat-template passthrough), from the same rule selection. Ponder sits above provider-level
reasoning controls: it decides *when* to invoke them, not just how much. Best-effort by design —
many open-weight models expose nothing here, and a rejected parameter retries without it rather
than losing the sample. `PONDER_NATIVE_EFFORT=0` turns it off.

---

## What each partner technology actually did

### Pydantic — the effort actuator

Effort is **not** an `if` branch in our code. It is a **Gateway rule**, selected per task:

- `ponder-cheap-answer-only` — answer only, no working, no preamble
- `ponder-deep-reason` — extended step-by-step reasoning, arithmetic and edge cases checked

`agent/worker.py` builds one **Pydantic AI** `Agent` per rule over the **Pydantic AI
Gateway**, which routes BYOK to our Modal-hosted model. Swapping effort means asking the
Gateway for a different rule — the agent code is identical on both paths. Every call path
is `Python agent → Pydantic AI → Pydantic AI Gateway → Modal-hosted open-weight model`; no
proprietary model is ever the worker.

**Guardrails** are Pydantic too: `pydantic_ai_harness.guardrails` supplies `InputGuardrail`,
`OutputGuardrail` and the secret/PII detectors, and the domain rule chooses which ones apply.
They run inside every Modal fan-out container as well as locally, so the checks travel with the
compute rather than sitting in front of it.

**Logfire** carries the whole story: `agent/events.py` writes one span per task with every
contract field on it, and `pydantic_ai` is instrumented, so the tokens and the rule that
produced them sit in the same trace.

Evidence: `uv run python scripts/prove_rule.py --task s01` runs one task with the rule off
and on, and writes both Logfire trace links and the measured token delta to
`artifacts/rule_proof.json`. It **refuses to run without real credentials** — it will not
manufacture trace links for a submission.

**Measured on task `s01`** ("A paediatric patient weighs 18 kg. The prescribed dose is 15 mg/kg.
What is the dose in mg?") — same prompt, same model, same endpoint; only the Gateway rule changes:

| Gateway rule | Tokens | GPU-seconds | Answer | Logfire trace |
| --- | --- | --- | --- | --- |
| `ponder-deep-reason` | 162 | 1.1792 | full worked derivation, then `270 mg` | [trace](https://logfire-eu.pydantic.dev/maddy-codes/ponder?q=trace_id%3D%2701a0b9e06b7c00fa1bd14fef6fd12c47%27) |
| `ponder-cheap-answer-only` | 91 | 1.0345 | `270 mg` | [trace](https://logfire-eu.pydantic.dev/maddy-codes/ponder?q=trace_id%3D%2701a0b9e070dbc7ce1a4f20a29972161d%27) |

**Token delta: -71 tokens (-43.8%)** — the rule, not the code,
moved the number. Both rules are ours; neither is the built-in warm-up rule.

### Modal — the compute fabric

`agent/modal_app.py` uses Modal for three different things, and the deep path needs all of them:

1. **`serve`** — a dense, single-GPU, open-weight instruct model (`Qwen/Qwen2.5-7B-Instruct`)
   behind an OpenAI-compatible vLLM endpoint. Deliberately not an MoE model: an MoE risks
   sitting unscheduled waiting for a multi-GPU slot during a timed demo.
2. **`sample_once` + `.map()`** — best-of-N **at request time**. "Think harder" becomes N real
   containers running concurrently, each executing the Pydantic AI agent against the Gateway.
   GPU-seconds are measured *inside* each container and returned, so `TaskEvent.samples[]`
   carries real numbers rather than an orchestrator's estimate. Consequence buys width: a
   high-stakes task gets more samples than a merely-hard one.
3. **`modal.Sandbox`** — executed verification, network-blocked, for high-stakes answers.

Modal is load-bearing here, not hosting: delete the fan-out and the deep path stops being deep.

### Gemini Flash — optional triage judge

`agent/triage.py` ships a heuristic scorer and a drop-in Gemini judge behind the same
interface. Set `GEMINI_API_KEY` and it takes over; unset, the heuristic runs. `GEMINI_MODEL`
pins the judge (default `gemini-3.6-flash`) — Google retires these faster than we rebuild,
and `gemini-2.5-flash` is already closed to new keys. Triage sees **only the prompt** — never
the dataset's `stakes_tag` or `hardness`, which are held out for scoring error placement.

The judge earns its place: swapping the heuristic for Gemini cut ponder's spend from 51% of
always-deep to **34%** with *identical* high-stakes accuracy (16/18), because it escalates
fewer tasks and still misses none of the expensive ones. It finds the money shot unaided —
on the 24 kg dosing task it returns difficulty 0.10, stakes 0.80.

---

## The idea, in one screen

```
Task in
  → triage        difficulty, stakes  (prompt text only)
  → budget        stakes can OVERRIDE difficulty
  → rules         a NAMED domain rule outranks the score, and can demand verification
  → spend         cheap: 1 call, answer-only rule
                  deep:  deep-reasoning rule + N Modal samples + sandbox if high-stakes
  → aggregate     majority vote across samples
  → verify        executed second derivation; disagreement is broken by a third, not obeyed
  → emit          ONE TaskEvent → Logfire + Convex + events.jsonl
```

The two cases a pure difficulty router gets backwards:

- **high-stakes, easy-looking** (`s01`: an 18 kg child, 15 mg/kg — one multiplication):
  ponder escalates anyway and executes the arithmetic before answering.
- **low-stakes, hard** (`h01`: the bat-and-ball puzzle): ponder deliberately does not spend.

## Running it

Everything runs with **zero credentials** in stub mode — the worker model is a deterministic
simulator behind the same interface, so the loop, the dashboard and the recording are all real.

```bash
uv sync --extra dev

uv run python -m agent.loop --strategy ponder --fresh   # one pass over the queue
uv run python -m agent.baselines --fresh                # cheap vs deep vs ponder -> artifacts/frontier.json
uv run pytest                                           # 35 tests

cd web && npm install && npm run dev                    # Mission Control on :3000
```

Going live:

```bash
cp .env.example .env            # fill in Logfire, Gateway, Modal, Convex
modal deploy agent/modal_app.py # endpoint URL -> MODEL_ENDPOINT_URL + Gateway BYOK provider
modal run agent/modal_app.py    # smoke: proves fan-out and sandbox are real
cd web && npx convex dev        # push web/convex/schema.ts + live subscription
PONDER_MODE=live uv run python scripts/prove_rule.py --task s01
```

## Mission Control

`web/` is a **renderer**: every pixel comes from a `TaskEvent` that the agent already emitted.
Four zones — Queue, Effort view (triage meters, the matched domain rule, the Gateway rule, Modal
samples lighting up, the sandbox tick), Cost-vs-accuracy frontier + live spend against an
always-deep counterfactual, and an Evidence strip with the two Logfire links and the token delta.

**The Policy panel** is the one surface that writes rather than renders, and deliberately so:
the domain rules are the product, and they belong to the domain expert, not the repo. It lists
every rule in precedence order with its trigger phrases, its budget, whether it executes to
verify, and its guardrails; rules can be added, reordered, disabled and deleted. A **test box**
dry-runs any prompt against the live policy and shows which rule fires — no model call, no
tokens, instant — so a rule can be written and checked in seconds and only the tasks that
follow cost anything.

It never parses `agent/rules.json` itself. It asks `agent.rules` — the same loader the loop
runs — and writes back through the same validation, so what the editor shows is provably what
the next task will be judged by rather than a second interpretation that can drift. Saves are
write-then-rename, because the agent may be mid-run and must never read half a policy.

**The Bench** — the docked right-hand rail takes one task, runs it through `POST /api/ask` →
`agent.ask --stream` → the same `run_task` the batch queue uses, and drops the resulting event
into the same Queue and Effort view. No special-casing: it triages, matches a rule, spends,
verifies and emits its one TaskEvent like any other task.

It is a rail rather than a box above the grid because a deep task takes real time — the fan-out
is N actual containers and the sandbox is an actual execution — so the run has to be legible
while it happens. `--stream` prints one NDJSON snapshot per *real* stage transition and the
bench renders those: triage lands first with difficulty and stakes, the matched rule and the
budget with it, then the sample bar fills in as each container returns, then the sandbox, then
the answer. The elapsed clock runs throughout. Nothing on that rail is synthesised — every line
reads a field the streamed `TaskEvent` already carries, so the renderer invariant holds for the
live path too.

Type a financial question that looks trivial and watch the rule overrule the score. (In stub
mode the model's *words* are the one thing the simulator cannot supply, so the answer field says
so; the decision, the rule, the fan-out width and the token and GPU numbers are all real.)

`events.jsonl` is written on every run regardless of what else is up, and the dashboard's
Replay mode plays it back. The demo never depends on a live GPU.

## Layout

```
agent/    settings, events (the TaskEvent contract + 3-sink emitter), tasks, triage, budget,
          rules.json (THE POLICY — authored, not coded) + rules.py (loads and compiles it),
          guardrails (Pydantic guards, selected per rule), ask (the ponder() entry point),
          govern (policy in front of someone else's agent), worker (stub | Gateway),
          aggregate, verify, sandbox, grader, loop, baselines, modal_app
examples/ governed_agent.py — an ordinary agent, then the same agent governed
web/convex/  schema.ts (taskEvents) + events.ts (upsert/list/clear)
web/      Next.js App Router · Mission Control
scripts/  prove_rule.py (Pydantic evidence), build_tasks.py
docs/     IMPLEMENTATION_PLAN.md   ·   PONDER_BUILD.md is the original brief
```
