# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Built and running end to end in stub mode. `PONDER_BUILD.md` is the original brief (phases,
timeboxes, submission checklist); `docs/IMPLEMENTATION_PLAN.md` maps those phases onto files.
Credential-blocked work remaining: deploy the Modal endpoint, create the two Gateway rules,
run `scripts/prove_rule.py` for the two Logfire trace links, push Convex.

**Stub mode is the default and it is not a mock of the loop** — only of the worker model.
`PONDER_MODE=live` swaps `agent/worker.py`'s seam to the real Gateway path; every other module
is unchanged. Never add a second code path for stub vs live outside that seam.

## What Ponder is

An agent that decides **how hard to think**. Each task is scored on `difficulty × stakes`,
which selects a compute budget: trivial items get one cheap call; hard or high-stakes items get
deep reasoning, parallel best-of-N sampling on Modal, and (high stakes only) an executed sandbox
verification. The claim being demonstrated is a cost/accuracy frontier — ponder ≈ always-deep
accuracy at a fraction of the compute, with the remaining errors concentrated on *low-stakes*
items.

## Invariants (violating these breaks the prize entries, not just the code)

1. **The worker model call path is fixed:** `Python agent → Pydantic AI → Pydantic AI Gateway →
   Modal-hosted open-weight model`. Never route the worker through a proprietary API. Gemini is
   permitted *only* as the optional triage judge, never as the worker.
2. **Two actuators are load-bearing.** The **Gateway rule** decides *how* the model thinks — effort
   is switched by selecting a rule, not by an `if` branch in agent code. **Modal** decides *how
   much* compute burns (runtime best-of-N fan-out + sandbox). Neither may degrade into "just
   model hosting" or "just a config toggle".
3. **Instrument once, fan out.** Every task emits exactly one `TaskEvent` to three sinks: Logfire
   span attributes, a Convex mutation, and an appended line in `events.jsonl`. Never reverse-query
   the Logfire API at runtime.
4. **`events.jsonl` is always written**, Convex up or down. It is the Replay file; the demo runs
   off a recorded known-good run, not live model calls.
5. **The dashboard is a pure renderer.** Every panel reads fields that `TaskEvent` already carries.
   If a panel would need new backend work, cut the panel.
6. **No auth, no Clerk, no services outside the locked stack.** Single user, single page.

## Architecture

```
Task in
  → triage.py    difficulty, stakes (0..1 each; crude scoring is fine)
  → budget = f(difficulty, stakes)          # stakes can override difficulty
  → spend:  cheap → 1 call, answer-only Gateway rule
            deep  → deep-reasoning Gateway rule + N parallel Modal samples (best-of-N)
                    + sandbox verification when stakes are high
  → aggregate → grade → emit ONE TaskEvent (Logfire + Convex + events.jsonl)
```

`baselines.py` replays the same queue under three strategies — `cheap`, `deep`, `ponder` — to
produce the frontier. The interesting demo cases are the two that a pure difficulty router gets
backwards: **high-stakes but easy-looking** (escalate anyway, verify in sandbox) and **low-stakes
but hard** (deliberately don't spend).

Split of responsibilities: **the agent is Python** (local or on Modal). **Convex + Next.js are the
app/transport layer only** — Vercel hosts the frontend, never the agent.

## The central contract

`TaskEvent` (defined in `agent/events.py`, mirrored by the Convex `taskEvents` table, rendered by
the web UI) is the one schema everything agrees on. Its full field list lives in
`PONDER_BUILD.md` §2 — define it before writing the loop, and change it in all three places at
once (Pydantic model → Convex schema → renderer) or not at all.

## Locked stack — do not substitute

Pydantic AI (agent) · Pydantic AI Gateway (effort rules, BYOK to the Modal endpoint) · Logfire
(traces + compute numbers) · Modal (GPU model endpoint, `.map()` fan-out, Sandboxes) · Convex
(transport) · Next.js App Router + Tailwind + Recharts (Mission Control) · plain Python grading.

Worker model must be an open-weight **dense single-GPU** instruct model (~7–14B). **Not** MoE —
an MoE model risks sitting unscheduled.

## Layout (target)

```
agent/    loop.py triage.py gateway.py modal_app.py events.py grader.py baselines.py tasks.jsonl
convex/   schema.ts events.ts
web/      app/page.tsx components/{Queue,EffortView,FrontierMeter,SpendCounter,EvidenceStrip}
events.jsonl   # recorded known-good run (Replay)
```

## Toolchain

```bash
uv sync --extra dev
uv run python -m agent.loop --strategy ponder --fresh   # queue run; --task <id> for one
uv run python -m agent.baselines --fresh                # frontier -> artifacts/frontier.json
uv run pytest                                           # 20 tests; -k budget for the thesis
uv run python scripts/build_tasks.py                    # regenerate agent/tasks.jsonl
uv run python scripts/prove_rule.py --task s01          # Pydantic evidence (needs live creds)
cd web && npm run dev                                   # Mission Control at :3000

modal deploy agent/modal_app.py                         # GPU endpoint + fan-out + sandbox
modal run agent/modal_app.py                            # smoke test both
npx convex dev                                          # push convex/schema.ts
```

`--fresh` truncates `events.jsonl`. The dashboard reads whatever is in it, so a baselines run
(all three strategies) is what you want recorded before a demo — the spend panel needs the
`deep` events to compute the always-deep counterfactual.

Env vars live in `.env` — see `PONDER_BUILD.md` §4 for the full list (`LOGFIRE_TOKEN`,
Gateway key, `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`, `MODEL_ENDPOINT_URL`, `CONVEX_DEPLOYMENT`,
`NEXT_PUBLIC_CONVEX_URL`, optional `GEMINI_API_KEY`).

## Build order

Phases are ordered by prize value, not by dependency comfort: **Phase 1 (Pydantic Gateway rule,
two Logfire trace links + token delta)** and **Phase 5 (Modal runtime best-of-N)** are the two
cash-banking phases and both come *before* the dashboard (Phase 6). Do not start a phase until
the previous phase's Done criteria in `PONDER_BUILD.md` §5 are met. Phase 3 (the consequence-aware
loop) is the core — protect it.

Artifacts that must survive to submission: both Logfire trace URLs (rule off / rule on), the
measured token delta, the custom rule itself (the built-in warm-up rule does not count), and a
recorded `events.jsonl`.
