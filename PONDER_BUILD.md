# PONDER — Build Brief for Claude Code

> Save this as `CLAUDE.md` at the repo root (Claude Code auto-loads it), or keep it as
> `PONDER_BUILD.md` and tell Claude Code: *"Follow PONDER_BUILD.md. Work phase by phase,
> in order. Do not start a phase until the previous phase's Done criteria are met."*

**What we're building:** *Ponder* — an agent that decides **how hard to think**. It scores each
task on **difficulty × stakes**, then allocates compute: trivial items get one cheap call;
hard or high-stakes items get deep reasoning, parallel best-of-N sampling, and (for high
stakes) an executed sandbox verification. Same accuracy as a full-effort agent at a fraction
of the compute — and the effort goes where being wrong actually hurts. A single dashboard
("Mission Control") shows it happening live.

**North star for the day:** win the two independently-judged cash side-tracks (Modal €1,500 +
Pydantic €1,500 = the controllable money), and be a credible finalist for free by building it well.

---

## 0. NON-NEGOTIABLES — read before writing any code

1. **Order is sacred.** Bank the two cash prizes first: **Phase 1 (Pydantic)** and **Phase 5
   (Modal)** come before the dashboard (**Phase 6**). A gorgeous dashboard over a broken core
   loses on technical execution *and* has nothing real to show.
2. **The worker model runs on Modal, through the Gateway.** The call path is always:
   `Python agent → Pydantic AI → Pydantic AI Gateway → Modal-hosted open-weight model`.
   Never route the worker through a proprietary API — that breaks *both* side prizes. (Gemini
   is allowed only as the optional triage *judge*, never the worker. See Phase 7.)
3. **Instrument once, fan out.** Every task emits exactly one `TaskEvent` → Logfire **and**
   Convex **and** `events.jsonl`. Do not reverse-query Logfire's API at runtime.
4. **Keep `events.jsonl` always.** It is the **Replay** file. The demo runs on a recorded
   known-good run, not on live model calls.
5. **Keep the real Logfire traces.** The Pydantic prize requires two trace links (rule off/on).
   Mission Control *presents* the numbers, but the real traces stay linkable.
6. **The dashboard is a renderer.** If a panel needs new backend work at build time, cut it.
   Everything it shows comes from `TaskEvent`s already being emitted.
7. **No auth, no Clerk, no extra services.** Single-user, single page, localhost/Replay demo.
   Do not add authentication, user accounts, or anything not in the stack below.

---

## 1. LOCKED TECH STACK — do not substitute


| Layer                   | Choice                                                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Agent framework         | **Pydantic AI** (typed agent, validated tool calls)                                                                                 |
| Effort actuator         | **Pydantic AI Gateway** (reasoning rules; BYOK to the Modal endpoint)                                                               |
| Observability           | **Logfire** (traces + compute numbers; source of the two trace links)                                                               |
| Model serving           | **Modal** — open-weight model on a GPU endpoint; `.map()` fan-out for best-of-N; **Sandboxes** for verification                    |
| Worker model            | An open-weight**dense single-GPU** instruct model (~7–14B) from Modal's library. **Not** an MoE model (risks sitting unscheduled). |
| Triage judge (optional) | **Gemini Flash** — difficulty × stakes scoring. Droppable.                                                                        |
| Backend / transport     | **Convex** — Python client writes `TaskEvent`s; Next.js subscribes reactively                                                      |
| Frontend                | **Next.js** (App Router) + **Tailwind** on **Vercel** (deploy is optional polish)                                                   |
| Charts                  | **Recharts**                                                                                                                        |
| Replay/persistence      | **`events.jsonl`** (always written, regardless of Convex)                                                                           |
| Grading                 | Plain Python (exact-match / executed check)                                                                                         |

**Split of responsibilities:** the **agent is Python** (runs locally or on Modal). **Convex +
Next.js are the app/transport layer only.** Vercel hosts the *frontend*, never the agent.
Localhost + Replay is the demo safety net even if Vercel/Convex are live.

---

## 2. ARCHITECTURE

```
Task in
  → Triage (difficulty, stakes)           # cheap fast pass; Gemini Flash or the open model
  → Budget = f(difficulty, stakes)        # cheap path | deep path; stakes can override difficulty
  → Spend:
      cheap path : 1 call, answer-only Gateway rule
      deep path  : deep-reasoning Gateway rule + N parallel samples on Modal (best-of-N)
                   + sandbox verification if stakes are high
  → Aggregate answer
  → Measure (Logfire: tokens, GPU-seconds, correct?)
  → emit TaskEvent → Logfire + Convex + events.jsonl
Compare always-cheap / always-deep / ponder → cost-vs-accuracy frontier
```

Two actuators are load-bearing: the **Gateway** decides *how* the model thinks (a rule, no code
branch); **Modal** decides *how much* compute it burns (parallel samples + sandbox). Remove
either and the idea collapses — that's what makes each a "best use", not an accessory.

### The `TaskEvent` contract (define this FIRST, in Phase 2 — everything renders it)

```python
from pydantic import BaseModel
from typing import Literal

class Sample(BaseModel):
    status: Literal["running", "done", "failed"]
    tokens: int = 0
    gpu_seconds: float = 0.0

class TaskEvent(BaseModel):
    id: str
    prompt_preview: str
    difficulty: float                 # 0..1 (triage)
    stakes: float                     # 0..1 (triage)
    budget: Literal["cheap", "deep"]
    rule_id: str                      # Gateway rule applied
    strategy: Literal["cheap", "deep", "ponder"]
    samples: list[Sample] = []
    sandbox_ran: bool = False
    sandbox_passed: bool | None = None
    answer: str | None = None
    correct: bool | None = None
    latency_ms: int = 0
    total_tokens: int = 0
    total_gpu_seconds: float = 0.0
    logfire_trace_url: str | None = None
    status: Literal["queued", "thinking", "verifying", "done"] = "queued"
```

The Convex `taskEvents` table mirrors these fields. The emitter writes the same object to all
three sinks (Logfire span attributes, Convex mutation, and an appended line in `events.jsonl`).

---

## 3. REPO LAYOUT

```
/agent
  loop.py          # orchestration: triage → budget → spend → measure → emit
  triage.py        # difficulty × stakes scoring (crude is fine)
  gateway.py       # Pydantic AI agent through the Gateway; rule selection per budget
  modal_app.py     # Modal: model endpoint + best-of-N fan-out + sandbox verify
  events.py        # TaskEvent model + emitter (Logfire + Convex + events.jsonl)
  grader.py        # exact-match / executed check
  baselines.py     # run cheap / deep / ponder over the queue; compute the frontier
  tasks.jsonl      # ~40 items: prompt, verifiable answer, stakes tag
/convex
  schema.ts        # taskEvents table
  events.ts        # mutation to upsert a TaskEvent; query to stream them
/web               # Next.js App Router (Mission Control)
  app/page.tsx     # the one screen
  components/      # Queue, EffortView, FrontierMeter, SpendCounter, EvidenceStrip
events.jsonl       # recorded known-good run (Replay)
.env
README.md          # names Modal + Pydantic and exactly what each did
```

---

## 4. ENV / SECRETS

```
LOGFIRE_TOKEN=
PYDANTIC_AI_GATEWAY_...=        # per the Gateway setup guide (BYOK provider = your Modal endpoint)
MODAL_TOKEN_ID=
MODAL_TOKEN_SECRET=
MODEL_ENDPOINT_URL=            # your deployed Modal model endpoint
GEMINI_API_KEY=               # optional (triage judge only)
CONVEX_DEPLOYMENT=
NEXT_PUBLIC_CONVEX_URL=
```

---

## 5. BUILD PHASES — recalibrated 11:50 → 18:00 (dev freeze 18:00 sharp)

> Each phase lists **Do** and **Done** (acceptance). Do not advance until **Done** is met.
> While the GPU provisions in Phase 0, scaffold `/convex` and `/web` in parallel — that's dead time otherwise.

### Phase 0 — Setup & de-risk · 11:50–12:15

- **Do:** Start the **Modal GPU provisioning first** (longest pole). In parallel: create the
  repo, Logfire account + Gateway, and scaffold Convex + Next. Deploy a dense single-GPU open
  model as a Modal endpoint; add it to the Gateway as a BYOK provider; run one call and see the
  trace land in Logfire.
- **Done:** one real request goes agent → Gateway → Modal model, and its trace is visible in Logfire.

### Phase 1 — BANK PYDANTIC (Layer 0) · 12:15–12:45  ★ money

- **Do:** Write one **custom** Gateway rule (answer-only / terse vs default reasoning). Run one
  task with the rule off, then on. Capture both Logfire trace URLs and the token delta. Screenshot the rule.
- **Done:** two distinct Logfire trace links saved + a measured token delta + rule screenshot.
  (Pydantic entry is now essentially complete. The built-in warm-up rule does NOT count — it must be yours.)

### Phase 2 — TaskEvent contract + queue + grader · 12:45–13:05

- **Do:** Implement `events.py` (the schema + the three-sink emitter). Build `tasks.jsonl`
  (~40 items with verifiable answers + stakes tags). Implement `grader.py`. Single-task runner
  emits a full `TaskEvent`.
- **Done:** running one task writes a valid `TaskEvent` to Logfire, Convex, and `events.jsonl`.

### Phase 3 — Consequence-aware loop (Layer 1) · 13:20–14:20  *(15-min break 13:05–13:20)*

- **Do:** `triage.py` scores difficulty × stakes (crude OK). `budget = f(difficulty, stakes)`,
  stakes able to override difficulty. Route to cheap vs deep via the Gateway rules.
- **Done:** every task in the queue produces a `TaskEvent` with difficulty, stakes, budget,
  answer, correct — end to end. **This is the core; protect this hour.**

### Phase 4 — Baselines + measurement · 14:20–15:00

- **Do:** `baselines.py` runs always-cheap / always-deep / ponder over the queue; collect
  accuracy + compute + error placement.
- **Done:** confirmed that ponder ≈ always-deep accuracy at lower compute **and** its errors sit
  on low-stakes items. If strategies don't separate, sharpen the difficulty/stakes spread NOW.

### Phase 5 — BANK MODAL (Layer 2) · 15:00–15:40  ★ money

- **Do:** Make "think harder" real runtime compute: the deep path fans out best-of-N across
  Modal containers at runtime (not a benchmark harness). Events carry per-sample timings + GPU-seconds.
- **Done:** a hard task visibly spends N parallel samples on Modal at runtime; GPU-seconds appear
  in its `TaskEvent`. (Modal is now load-bearing, not just model hosting.)

### Phase 6 — Mission Control (Layer 3) · 15:50–16:50  *(10-min break 15:40–15:50)*

- **Do:** Next.js page subscribing to Convex. Four zones: **Queue** (left), **Effort view**
  (centre — triage scores, rule applied, samples lighting up, sandbox ticking), **Frontier +
  Spend meters** (top-right), **Evidence strip** (bottom — two Logfire trace links + token delta).
  Renderer only — all data comes from `TaskEvent`s.
- **Done:** the dashboard replays a run end to end and the money-shot frame (a high-stakes,
  easy-looking task escalating) is unmistakable. **Hard-timebox 60 min.**

### Phase 7 — Sandbox verify + Replay + optional judge · 16:50–17:20

- **Do:** Sandbox-executed verification on high-stakes answers (Layer 4) **if ahead**. Record a
  known-good `events.jsonl`; wire the Live/Replay toggle. If time: swap triage to a Gemini Flash
  judge for the third partner tech.
- **Done:** the demo runs entirely from the recorded `events.jsonl`.

### Phase 8 — Freeze & rehearse · 17:20–17:50 · buffer 17:50–18:00

- **Do:** Stop building at 18:00. Run the 2-minute demo on Replay twice. Final pass on the
  money-shot frame and the evidence links.
- **Done:** a clean, repeatable 2-minute run.

---

## 6. DEMO SCRIPT (2 min)

1. **10s** — the problem: naive agent over-spends (the spend counter climbing).
2. **40s** — run a mixed queue: breeze past trivial items on one cheap call; escalate a hard one, samples light up.
3. **30s** — the money shot: a **high-stakes, easy-looking** item where it spends anyway and
   sandbox-verifies; a **low-stakes, hard** item where it deliberately doesn't. "A difficulty
   router gets both backwards."
4. **20s** — the frontier: Ponder on the always-deep accuracy line at a fraction of the compute; every miss is low-stakes.
5. **20s** — flash the two Logfire traces (rule off/on) + token delta.

---

## 7. SUBMISSION CHECKLIST (18:00–19:00) — submissions close 19:00

- [ ]  2-minute video demo (Loom or equivalent)
- [ ]  Public GitHub repo, full source
- [ ]  README naming **Modal** and **Pydantic** with exactly what each did
- [ ]  **Pydantic:** the rule (screenshot/text) + before/after + **two Logfire trace links** + token delta; guardrail bonus only if built
- [ ]  **Modal:** confirm Modal use; point to the runtime best-of-N fan-out and sandbox verification — not just model hosting
- [ ]  Captain checked in at the desk
- [ ]  Everything submitted **before** 19:00 — not at 18:59
