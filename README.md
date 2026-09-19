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
# result.matched_rule  — which domain rule fired, if any ("financial_total")
# result.rule_reason   — why that rule exists, and what it overrode
# result.budget        — "cheap" or "deep"
# result.verified      — True if a sandbox executed and confirmed it
# result.event         — the full TaskEvent, already in Logfire, Convex and events.jsonl
```

```bash
uv run python -m agent.ask "What is the total cost of 3 items at 4.50 each?"
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

## The rule layer

`agent/rules.py` holds a short list of **named, human-authored domain rules**. Each one matches
on the prompt — the same text triage sees, never the held-out ground truth — and states outright
what the match buys:

| rule | budget | verify | why |
|---|---|---|---|
| `clinical_dose` | deep | ✅ | dosing arithmetic is executed before it is trusted, however simple the sum |
| `safety_margin` | deep | ✅ | load, tolerance and timing margins — a plausible-looking number is the failure mode |
| `financial_total` | deep | ✅ | financial totals are always deep-verified regardless of apparent difficulty |
| `casual_lookup` | cheap | — | casual factual lookups never warrant deep reasoning |

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

**Logfire** carries the whole story: `agent/events.py` writes one span per task with every
contract field on it, and `pydantic_ai` is instrumented, so the tokens and the rule that
produced them sit in the same trace.

Evidence: `uv run python scripts/prove_rule.py --task s01` runs one task with the rule off
and on, and writes both Logfire trace links and the measured token delta to
`artifacts/rule_proof.json`. It **refuses to run without real credentials** — it will not
manufacture trace links for a submission.

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
          rules (named domain rules), ask (the ponder() entry point), worker (stub | Gateway),
          aggregate, verify, sandbox, grader, loop, baselines, modal_app
web/convex/  schema.ts (taskEvents) + events.ts (upsert/list/clear)
web/      Next.js App Router · Mission Control
scripts/  prove_rule.py (Pydantic evidence), build_tasks.py
docs/     IMPLEMENTATION_PLAN.md   ·   PONDER_BUILD.md is the original brief
```
