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
5. **The dashboard is a pure renderer.** Every panel reads fields that `TaskEvent` already carries;
   all aggregation lives in `web/lib/derive.ts` as pure functions over `TaskEvent[]`.
   If a panel would need new backend work, cut the panel.
   This holds for the live path too: the Bench rail renders `agent.ask --stream`, which is the
   loop's existing `Emitter.progress()` calls echoed to stdout as NDJSON. A stage appears
   because the agent reached it — never because the client guessed, timed out, or interpolated.
   The last streamed line is the durable `TaskEvent`; there is still exactly one of those.
   It is also *navigable*: any task is clickable from the queue, the decision map or the task log,
   and opens in the console detail pane. Clicking never mutates the recording.

## Audit output

`TaskEvent` is the audit record, so both audit surfaces are pure serialisations of it — no route,
no recomputation, nothing inferred.

- **Log export** (`lib/export.ts`, the Export menu on the task log): CSV (21 audit columns, one row
  per task, BOM'd for Excel), JSON with an export envelope, and JSONL identical in shape to
  `events.jsonl`. Exports either the filtered view or the whole run.
- **Decision receipt** (`lib/receipt.ts`, `components/receipt-dialog.tsx`): a per-exchange document
  — request, triage, policy (which rule fired and whether it overrode the score), compute
  committed, verification, result, provenance. It carries a SHA-256 fingerprint of the canonical
  event, so the receipt number and digest are stable for a given record and a changed record shows
  a different digest. Copy as Markdown, save `.md`/`.json`, or print — the print stylesheet in
  `globals.css` drops the app and lays the receipt out on white. A receipt for a task whose
  `status` is not `done` is stamped **provisional** rather than blocked.
6. **No auth, no Clerk, no services outside the locked stack.** Single user, single page.

## Architecture

```
Task in
  → triage.py    difficulty, stakes (0..1 each; crude scoring is fine)
  → budget = f(difficulty, stakes)          # stakes can override difficulty
  → rules.py     a NAMED domain rule outranks that score, and may demand verification
  → spend:  cheap → 1 call, answer-only Gateway rule
            deep  → deep-reasoning Gateway rule + N parallel Modal samples (best-of-N)
                    + sandbox verification when stakes are high
  → aggregate → grade → emit ONE TaskEvent (Logfire + Convex + events.jsonl)
```

`baselines.py` replays the same queue under three strategies — `cheap`, `deep`, `ponder` — to
produce the frontier. The interesting demo cases are the two that a pure difficulty router gets
backwards: **high-stakes but easy-looking** (a one-step dose sum — escalate anyway, verify in
sandbox) and **low-stakes but hard** (ward rota and stock puzzles — deliberately don't spend).
The hard/low quadrant is clinically *flavoured* but clinically *harmless* on purpose: it is
the only way to show the policy reads consequence rather than hospital vocabulary. Scope and
stakes therefore use separate lexicons — sterilising trays is in scope but not high-stakes.

Split of responsibilities: **the agent is Python** (local or on Modal). **Convex + Next.js are the
app/transport layer only** — Vercel hosts the frontend, never the agent.

## The rule layer (the differentiator)

Reasoning-effort control is a shipped provider API parameter, and answer-compliance checking is
a product category. Neither connects a **named domain rule** to **how much the model reasons and
verifies before its answer is trusted**. `agent/rules.py` is that connective layer, and it is
the thing to protect when pitching: without it Ponder reads as difficulty-based routing.

The shipped policy is clinical: `paediatric_dose`, `high_alert_medication`,
`infusion_rate`, `renal_dose_adjustment`, `dose_dispensing` (escalating), `patient_record`
(PII-blocking), then `ward_estimate` and `clinical_reference` (deliberately cheap).

**The rules are data.** `agent/rules.json` is the policy; `agent/rules.py` only loads and
compiles it; Mission Control's Policy panel authors it through `web/app/api/rules/route.ts`,
which shells out to `python -m agent.rules --json` rather than parsing the file itself — one
loader, no drift. The loader reloads on mtime, so a saved rule binds on the next task.

A rule has three clauses: `budget` (how hard to think), `sandbox_verify` (whether the answer is
executed before it is trusted) and `guardrails` (which named checks the answer must clear).
Named rules match on the prompt only, are declared escalate-first, and **outrank** the numeric
score; with no match `budget = f(difficulty, stakes)` decides as before. `matched_rule` and
`rule_reason` on `TaskEvent` are the audit trail, and `rule_reason` names what the score alone
would have spent whenever the two disagreed. Baselines (`cheap`/`deep`) must never consult the
rules — `loop.plan()` gates that on `strategy == "ponder"`.

## Guardrails (`agent/guardrails.py`)

The domain is **medication safety**. Guards encode published clinical standards, not
generic output-quality heuristics:

| guard | on failure | catches |
|---|---|---|
| `numeric_answer_present` | retry | a dose question answered in prose |
| `units_present` | retry | a quantity with no unit |
| `no_hedging` | retry | "roughly", "I think" — a dose is not an estimate |
| `safe_dose_notation` | retry | ISMP *Do Not Use* list: `1.0 mg`, `.5 mg`, `10U`, `IU`, `µg`, `QD` |
| `no_patient_identifiers` | **block** | NHS number (Modulus 11 checked), phone, MRN, DOB, postcode, email |
| `shows_working` | retry | a deep-budget answer that only asserts a number |
| `health_topics_only` | **block**, on the **prompt** | anything that is not a clinical question |

First-party Pydantic: `InputGuardrail`/`OutputGuardrail`/`detectors` from
`pydantic_ai_harness.guardrails`, enforced at two points. Per call they are attached via
Pydantic AI's `capabilities` parameter (construction-time in `worker._agent_for`, per-run
in `govern`), so the framework redacts prompts and turns a failed output check into a real
`ModelRetry`. Then `loop._gate` runs the same guards once over the *aggregated* answer,
which no per-call guard ever saw.

**A trip escalates rather than refuses.** A guardrail failure on a cheap answer is treated
as evidence the task was underfunded: the budget goes to deep and the fan-out re-runs
(`TaskEvent.guardrail_escalated`). Escalation fires at most once and only upward from
cheap. The two `block` guards are the exceptions, and they block because neither failure
can be walked back by spending more: a disclosure has already happened, and an off-topic
question has no clinical answer at any budget.

**Stage matters.** `health_topics_only` runs on the *prompt*, not the answer — scope is an
input concern, and checking it on the way out means the tokens are already spent. The
framework enforces it: `InputGuardrail` turns a `block` into `SkipModelRequest`, so the
model call is never issued (`tests/test_guardrails.py` asserts the call count is zero) and
the harness emits its own `trace_block` span. `GuardSpec.stage` keeps input guards out of
the output chain; `check_input()` is the loop-level mirror so the stub worker and any
supplied `sampler` behave identically.

**Scope is policy-level, not per-rule.** An off-topic prompt matches no clinical rule by
definition, so it is declared once under `"scope"` in `agent/rules.json` and rides on every
decision, matched or not (`rules.scope_guardrails()`).

**This layer is not the gateway.** These guards run in our process. Stopping patient data
from *reaching* a model is a Pydantic AI **Gateway protection**, configured in the Logfire
UI — see `docs/GATEWAY_GUARDRAILS.md`. The harness's own PII detector does **not** catch UK
phone or NHS numbers, which is why both layers exist. The hackathon guardrail bonus is
asking for the gateway one.

## `govern()` (`agent/govern.py`)

The product surface: Ponder's policy in front of a Pydantic AI agent *someone else wrote*. It
never mutates that agent — guardrails ride on the per-run `capabilities` parameter, effort on
`model_settings`. It is **not** a second pipeline: it supplies a `sampler` to the same
`run_task`, so governed calls get the same triage, rules, guardrail gate, sandbox and single
TaskEvent. `examples/governed_agent.py` is the runnable demo. The `sampler` parameter on
`run_task` is the only extension seam in the loop — keep it that way.

`agent/ask.py` exposes `ponder(prompt)`: the documented drop-in entry point, used by the README
snippet, the CLI, and Mission Control's single-task box. It wraps a typed prompt as a `Task` with
no reference answer and hands it to the same `run_task`. A reference-free task grades to `None`
(ungraded, not a miss), and the stub worker says outright that it has no completion to imitate.

## The central contract

`TaskEvent` (defined in `agent/events.py`, mirrored by the Convex `taskEvents` table, rendered by
the web UI) is the one schema everything agrees on. Its full field list lives in
`PONDER_BUILD.md` §2 — define it before writing the loop, and change it in all three places at
once (Pydantic model → Convex schema → renderer) or not at all.

## Locked stack — do not substitute

Pydantic AI (agent) · Pydantic AI Harness (guardrails) · Pydantic AI Gateway (effort rules,
BYOK to the Modal endpoint) · Logfire
(traces + compute numbers) · Modal (GPU model endpoint, `.map()` fan-out, Sandboxes) · Convex
(transport) · Next.js App Router + Tailwind + Recharts (Mission Control) · plain Python grading.
The UI layer is shadcn/ui on Tailwind v4 tokens: `components/ui/*` is copied-in source, not a
dependency. Light and dark are both first-class (next-themes writes `.dark` on `<html>`; the switch
lives in the header), so every colour comes from a token defined for *both* modes in
`app/globals.css` — `--rule`, `--deep`, `--cheap`, `--stakes`, `--difficulty`, `--live`, `--ok`,
`--miss` for UI text and chips, and a separate `--chart-1..5` set for chart marks. The accent is
the brand indigo sampled off `logo.png` (`#3f3bfc`), and dark mode's ground is the logo's own ink
(`#080e21`). Logo assets are generated from that one file: `web/public/ponder-{lockup,mark}.png`
plus `-dark` variants (the ink is recoloured, never CSS-inverted — that would flip the blue), and
`web/app/{icon,apple-icon}.png` which Next serves as the favicons. No ad-hoc hex,
no `zinc-*`, and never a UI accent used as a mark colour: the chart steps are tuned against the
chart surface, the UI accents against body text.

Worker model must be an open-weight **dense single-GPU** instruct model (~7–14B). **Not** MoE —
an MoE model risks sitting unscheduled.

## Layout (target)

```
agent/    loop.py triage.py rules.py rules.json guardrails.py ask.py govern.py
          gateway.py modal_app.py events.py grader.py baselines.py tasks.jsonl
examples/ governed_agent.py
web/convex/ schema.ts events.ts   # inside web/: the Next client imports _generated
web/      app/{page.tsx,layout.tsx,globals.css} app/api/ask/route.ts
          lib/{types,derive,useRun}.ts       # derive.ts holds every aggregate the panels read
          components/{site-header,theme-toggle,theme-provider,primitives}
          components/{queue-list,task-detail,task-table,rule-ledger,bench,evidence-bar}
          components/{receipt-dialog,export-menu}   lib/{receipt,export}.ts
          components/rule-editor.tsx  app/api/rules/route.ts   # the Policy panel
          components/charts/{spend,budget,decision-map,frontier,stakes-accuracy}-chart.tsx
          components/ui/*   # shadcn/ui (base-nova, Base UI primitives) -- owned source, edit freely
events.jsonl   # recorded known-good run (Replay)
```

## Toolchain

```bash
uv sync --extra dev
uv run python -m agent.loop --strategy ponder --fresh   # queue run; --task <id> for one
uv run python -m agent.baselines --fresh                # frontier -> artifacts/frontier.json
uv run pytest                                           # 35 tests; -k budget for the thesis
uv run python -m agent.ask "..."                        # one prompt through the same pipeline
uv run python scripts/build_tasks.py                    # regenerate agent/tasks.jsonl
uv run python scripts/prove_rule.py --task s01          # Pydantic evidence (needs live creds)
cd web && npm run dev                                   # Mission Control at :3000

modal deploy agent/modal_app.py                         # GPU endpoint + fan-out + sandbox
modal run agent/modal_app.py                            # smoke test both
cd web && npx convex dev                                # push web/convex + codegen
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
