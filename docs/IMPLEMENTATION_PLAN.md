# Ponder — Implementation Plan

Companion to `PONDER_BUILD.md` (the brief, which owns *why* and *when*). This file owns
*what to write, file by file*, and the order to write it in.

**Legend:** `[offline]` = buildable and runnable with zero credentials · `[creds]` = needs a real
token before it can run · `★` = banks a cash prize.

---

## Guiding decision: every phase ships an offline path

Credentialed services (Modal GPU, Gateway, Logfire, Convex) each have a window where they are
unavailable — provisioning, rate limits, venue wifi. So every module is written against a small
seam with two implementations:

| Seam | Real | Offline |
|---|---|---|
| Worker model | Gateway → Modal endpoint | `StubModel` — deterministic, seeded by task id |
| Fan-out | `modal.Function.map()` | `ThreadPoolExecutor` over the same call |
| Sandbox | `modal.Sandbox` | `subprocess` with a timeout |
| Logfire | real spans | no-op if `LOGFIRE_TOKEN` unset |
| Convex | `ConvexClient.mutation` | skipped if `CONVEX_URL` unset |
| `events.jsonl` | **always written** | **always written** |

`PONDER_MODE=stub|live` selects it globally; individual sinks degrade on their own if their env
var is missing. This is what makes Replay honest — the same code path produced the recording.

---

## Phase A — Skeleton `[offline]` · **DONE**

- `pyproject.toml` — uv project, Python 3.12 (3.14 is ahead of pydantic-ai/modal wheels).
- `.env.example`, `.gitignore`, `git init`.
- `agent/settings.py` — one `Settings` object reading `.env`; exposes `mode`, per-sink
  enable flags, model/endpoint names. Everything else imports settings, never `os.environ`.

**Done:** `uv run python -c "from agent.settings import settings; print(settings)"` prints a
resolved config with no credentials present.

## Phase B — `TaskEvent` contract + sinks `[offline]` — *brief Phase 2* · **DONE**

- `agent/events.py` — `Sample`, `TaskEvent` exactly as the brief §2 specifies; `Emitter` with
  three sinks (Logfire span attrs, Convex mutation, `events.jsonl` append). One `emit()` per task,
  plus `update()` for in-flight status pushes so the dashboard animates rather than snapping.
- `agent/tasks.jsonl` — 40 items: `{id, prompt, answer, stakes_tag, kind}`. Spread deliberately
  across the 2×2 of difficulty × stakes, because Phase E's separation depends on that spread.
- `agent/grader.py` — `exact` (normalised string/number match) and `exec` (run candidate code
  against assertions) graders, dispatched on `kind`.

**Done:** one task run writes a valid `TaskEvent` line to `events.jsonl`; Logfire/Convex are
attempted and skipped cleanly when unset.

## Phase C — Gateway effort rules `[creds]` ★ — *brief Phase 1* · **CODE DONE, NEEDS CREDS**

- `agent/gateway.py` — Pydantic AI `Agent` built over the Gateway with BYOK to the Modal
  endpoint. Two **custom** rules: `ponder-cheap-answer-only` (terse, answer only, no reasoning)
  and `ponder-deep-reason` (extended reasoning). Rule id travels into the `TaskEvent`.
- `scripts/prove_rule.py` — runs one fixed task twice, rule off then on, prints both Logfire
  trace URLs and the token delta, writes `artifacts/rule_proof.json`.

**Done:** two distinct trace links + measured token delta saved to `artifacts/`. This is the
Pydantic submission evidence; capture the rule screenshot at the same time.

## Phase D — Triage + the consequence-aware loop `[offline]` — *brief Phase 3, the core* · **DONE**

- `agent/triage.py` — scores `difficulty` and `stakes` in 0..1. Heuristic scorer by default
  (keyword/structure signals + the task's `stakes_tag`); optional Gemini Flash judge behind the
  same interface.
- `agent/budget.py` — `budget(difficulty, stakes) -> "cheap" | "deep"`, where **stakes can
  override difficulty**: an easy-looking item above the stakes threshold still escalates. This
  one function is the whole thesis; it gets its own unit tests.
- `agent/loop.py` — triage → budget → spend → aggregate → grade → emit. Async, bounded
  concurrency over the queue.

**Done:** every one of the 40 tasks yields a complete `TaskEvent` with difficulty, stakes,
budget, answer, correct.

## Phase E — Modal: real runtime compute `[creds]` ★ — *brief Phase 5* · **CODE DONE, NEEDS DEPLOY**

- `agent/modal_app.py` — three things, not one:
  1. a vLLM server on a dense ~7–14B single-GPU instruct model (**not** MoE), as the OpenAI-
     compatible endpoint the Gateway points at;
  2. `sample_once` as a Modal Function, fanned out with `.map()` for best-of-N **at request
     time** — this is what makes Modal load-bearing rather than hosting;
  3. `verify_in_sandbox` using `modal.Sandbox` to actually execute high-stakes answers.
- Per-sample `tokens` and `gpu_seconds` are measured inside the container and returned, so
  `TaskEvent.samples[]` carries real numbers.

**Done:** a hard task visibly spends N parallel containers; GPU-seconds land in its `TaskEvent`.

## Phase F — Baselines + frontier `[offline]` — *brief Phase 4* · **DONE — frontier holds**

- `agent/baselines.py` — runs the queue under `cheap`, `deep`, `ponder`; reports accuracy,
  total tokens, total GPU-seconds, and **error placement** (what fraction of misses were
  low-stakes). Writes `artifacts/frontier.json`.

**Done:** ponder sits on the always-deep accuracy line at materially lower compute, and its
errors are concentrated in low-stakes items. If the strategies don't separate, widen the
difficulty/stakes spread in `tasks.jsonl` immediately — that is a data problem, not a code one.

## Phase G — Convex + Mission Control `[offline-capable]` — *brief Phase 6* · **DONE (Convex push pending)**

- `convex/schema.ts` — `taskEvents` table mirroring `TaskEvent`, indexed by `id`.
- `convex/events.ts` — `upsert` mutation + `list` query.
- `web/` — Next.js App Router single page, four zones: **Queue** (left), **Effort view**
  (centre: triage scores, rule applied, samples lighting up, sandbox tick), **Frontier + Spend**
  (top-right), **Evidence strip** (bottom: two Logfire links + token delta).
- `web/lib/source.ts` — Live (Convex subscription) vs **Replay** (streams `events.jsonl`
  through a route handler on a timer). The dashboard cannot tell the difference; the toggle is
  the whole safety net.

**Done:** the dashboard replays a full run, and the money-shot frame — a high-stakes,
easy-looking task escalating — is unmistakable. Hard 60-minute box.

## Phase H — Sandbox verify, Replay recording, optional judge — *brief Phase 7* · **DONE**

- Wire `verify_in_sandbox` into the deep path for high-stakes items only.
- Record a known-good `events.jsonl` and commit it.
- If ahead: swap triage to the Gemini Flash judge.

**Done:** the demo runs entirely off the recorded `events.jsonl`.

## Phase I — Freeze — *brief Phase 8* · **README done; rehearsal pending**

`README.md` naming Modal and Pydantic and exactly what each did; both trace links; token delta;
rule screenshot; two clean Replay rehearsals. Stop building at 18:00.

---

## Build order actually followed

A → B → D (stub worker) → F → then C and E the moment credentials exist → G → H → I.

This inverts the brief's prize-first ordering *only* because C and E are credential-blocked: the
loop is written and proven against the stub first so that when the Modal endpoint comes up, the
prize phases are a matter of pointing the seam at the real thing, not writing new logic.


---

## Status at handover

Measured on the recorded run (`artifacts/frontier.json`), stub worker, 40 tasks:

| strategy | high-stakes acc | tokens | gpu-s | low-stakes share of misses |
|---|---|---|---|---|
| cheap | 67% | 2,317 | 32 | 65% |
| deep | 89% | 182,377 | 2,508 | 67% |
| ponder | **89%** | **89,283** | **1,239** | **82%** |

`VERDICT: frontier holds` — ponder matches always-deep on high stakes at 51% of the compute,
and 82% of its remaining errors are low-stakes. 20 tests pass. `web` typechecks and builds.

**The three credential-blocked steps, in the order they unblock value:**

1. `modal deploy agent/modal_app.py` → endpoint URL into `MODEL_ENDPOINT_URL` and into the
   Gateway as a BYOK provider. (Longest pole; start it first.)
2. Create the two custom Gateway rules in the console — named to match `GATEWAY_RULE_CHEAP`
   and `GATEWAY_RULE_DEEP`. Screenshot them. Confirm how the Gateway expects a rule to be
   selected per request and adjust `GATEWAY_RULE_HEADER` (default `X-Gateway-Rule`) —
   `agent/worker.py::_agent_for` is the only place that needs to change.
3. `PONDER_MODE=live uv run python scripts/prove_rule.py --task s01` → writes the two Logfire
   trace links and the token delta the Pydantic entry needs, and lights up the dashboard's
   evidence strip.
