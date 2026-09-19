# Ponder — an agent that decides how hard to think

Ponder scores every task on **difficulty × stakes** and allocates compute accordingly.
Trivial items get one cheap call. Hard or high-stakes items get a deep-reasoning rule,
best-of-N sampling fanned out across Modal containers, and — when being wrong is
expensive — an answer that is **executed in a sandbox before it is trusted**.

The result is not "more accurate". It is **the same accuracy where it matters, for half
the compute, with the remaining errors pushed onto tasks nobody is harmed by**.

Measured over a 40-task queue (`agent/tasks.jsonl`, `artifacts/frontier.json`):

| strategy | high-stakes accuracy | tokens | GPU-seconds | misses that were low-stakes |
|---|---|---|---|---|
| always-cheap | 67% | 2,317 | 32 | 65% |
| always-deep | 89% | 182,377 | 2,508 | 67% |
| **ponder** | **89%** | **89,283** | **1,239** | **82%** |

Ponder holds always-deep's high-stakes accuracy on **51% of the compute**, and 82% of the
errors it does make are on things like a lily-pad riddle.

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

`agent/triage.py` ships a heuristic scorer and a drop-in `gemini-2.5-flash` judge behind the
same interface. Set `GEMINI_API_KEY` and it takes over; unset, the heuristic runs. Triage
sees **only the prompt** — never the dataset's `stakes_tag` or `hardness`, which are held out
for scoring error placement.

---

## The idea, in one screen

```
Task in
  → triage        difficulty, stakes  (prompt text only)
  → budget        stakes can OVERRIDE difficulty
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
uv run pytest                                           # 20 tests

cd web && npm install && npm run dev                    # Mission Control on :3000
```

Going live:

```bash
cp .env.example .env            # fill in Logfire, Gateway, Modal, Convex
modal deploy agent/modal_app.py # endpoint URL -> MODEL_ENDPOINT_URL + Gateway BYOK provider
modal run agent/modal_app.py    # smoke: proves fan-out and sandbox are real
npx convex dev                  # push convex/schema.ts
PONDER_MODE=live uv run python scripts/prove_rule.py --task s01
```

## Mission Control

`web/` is a **renderer**: every pixel comes from a `TaskEvent` that the agent already emitted.
Four zones — Queue, Effort view (triage meters, the Gateway rule, Modal samples lighting up,
the sandbox tick), Cost-vs-accuracy frontier + live spend against an always-deep
counterfactual, and an Evidence strip with the two Logfire links and the token delta.

`events.jsonl` is written on every run regardless of what else is up, and the dashboard's
Replay mode plays it back. The demo never depends on a live GPU.

## Layout

```
agent/    settings, events (the TaskEvent contract + 3-sink emitter), tasks, triage, budget,
          worker (stub | Gateway), aggregate, verify, sandbox, grader, loop, baselines, modal_app
convex/   schema.ts (taskEvents) + events.ts (upsert/list)
web/      Next.js App Router · Mission Control
scripts/  prove_rule.py (Pydantic evidence), build_tasks.py
docs/     IMPLEMENTATION_PLAN.md   ·   PONDER_BUILD.md is the original brief
```
