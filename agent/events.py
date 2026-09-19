"""The TaskEvent contract and the one emitter that fans it out to three sinks.

Invariant (PONDER_BUILD.md §0.3): a task produces exactly ONE durable TaskEvent —
one Logfire span, one Convex row, one events.jsonl line. `Emitter.progress()` is the
single exception and it touches only Convex, mutating the same row in place so the
live dashboard can animate. Nothing reverse-queries Logfire at runtime.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Literal

from pydantic import BaseModel, Field

from agent.settings import EVENTS_PATH, settings


class Sample(BaseModel):
    status: Literal["running", "done", "failed"]
    tokens: int = 0
    gpu_seconds: float = 0.0


class TaskEvent(BaseModel):
    id: str
    prompt_preview: str
    difficulty: float = 0.0           # 0..1 (triage)
    stakes: float = 0.0               # 0..1 (triage)
    budget: Literal["cheap", "deep"] = "cheap"
    rule_id: str = ""                 # Gateway rule applied
    strategy: Literal["cheap", "deep", "ponder"] = "ponder"
    samples: list[Sample] = Field(default_factory=list)
    sandbox_ran: bool = False
    sandbox_passed: bool | None = None
    answer: str | None = None
    correct: bool | None = None
    latency_ms: int = 0
    total_tokens: int = 0
    total_gpu_seconds: float = 0.0
    logfire_trace_url: str | None = None
    status: Literal["queued", "thinking", "verifying", "done"] = "queued"
    ts: float = Field(default_factory=time.time)  # ordering for replay; the only addition

    @property
    def escalated_on_stakes(self) -> bool:
        """The money shot: spent deep compute on something that looked easy."""
        return self.budget == "deep" and self.difficulty < settings.difficulty_deep

    def roll_up(self) -> None:
        """Recompute the totals from the samples. Call once before the durable emit."""
        self.total_tokens = sum(s.tokens for s in self.samples)
        self.total_gpu_seconds = round(sum(s.gpu_seconds for s in self.samples), 4)


# --------------------------------------------------------------------------- sinks


class JsonlSink:
    """Always on. This file is the Replay recording."""

    name = "jsonl"
    enabled = True

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def write(self, event: TaskEvent) -> None:
        line = event.model_dump_json()
        with self._lock:
            with EVENTS_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


class LogfireSink:
    """One span per task, every contract field as a span attribute."""

    name = "logfire"

    def __init__(self) -> None:
        self.enabled = settings.use_logfire
        self._logfire = None
        if not self.enabled:
            return
        try:
            import logfire

            logfire.configure(token=settings.logfire_token, service_name="ponder", console=False)
            logfire.instrument_pydantic_ai()
            self._logfire = logfire
        except Exception as exc:  # pragma: no cover - credential/network dependent
            print(f"[emitter] logfire disabled: {exc}")
            self.enabled = False

    def write(self, event: TaskEvent) -> None:
        if not self.enabled or self._logfire is None:
            return
        payload = event.model_dump()
        payload["samples"] = [s.model_dump() for s in event.samples]
        with self._logfire.span(
            "ponder.task {task_id}",
            task_id=event.id,
            **{k: v for k, v in payload.items() if k not in {"id", "samples"}},
            n_samples=len(event.samples),
            sample_detail=payload["samples"],
        ):
            pass


class ConvexSink:
    """Upserts by task id, so the row count still matches the event count."""

    name = "convex"

    def __init__(self) -> None:
        self.enabled = settings.use_convex
        self._client = None
        if not self.enabled:
            return
        try:
            from convex import ConvexClient

            self._client = ConvexClient(settings.convex_url)
        except Exception as exc:  # pragma: no cover - credential/network dependent
            print(f"[emitter] convex disabled: {exc}")
            self.enabled = False

    def write(self, event: TaskEvent) -> None:
        if not self.enabled or self._client is None:
            return
        try:
            self._client.mutation("events:upsert", {"event": json.loads(event.model_dump_json())})
        except Exception as exc:  # pragma: no cover
            print(f"[emitter] convex write failed for {event.id}: {exc}")


# --------------------------------------------------------------------------- emitter


class Emitter:
    def __init__(self) -> None:
        self.jsonl = JsonlSink()
        self.logfire = LogfireSink()
        self.convex = ConvexSink()

    @property
    def active(self) -> list[str]:
        return [s.name for s in (self.jsonl, self.logfire, self.convex) if s.enabled]

    def progress(self, event: TaskEvent) -> None:
        """Live-only in-flight push. Convex mutates the same row; nothing durable moves."""
        self.convex.write(event)

    def emit(self, event: TaskEvent) -> TaskEvent:
        """The durable write: one span, one row, one line."""
        event.roll_up()
        self.logfire.write(event)
        self.convex.write(event)
        self.jsonl.write(event)
        return event


_emitter: Emitter | None = None


def get_emitter() -> Emitter:
    global _emitter
    if _emitter is None:
        _emitter = Emitter()
    return _emitter


def load_events(path=EVENTS_PATH) -> list[TaskEvent]:
    """Read back a recording (used by baselines and the Replay route)."""
    if not path.exists():
        return []
    out: list[TaskEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(TaskEvent.model_validate_json(line))
    return out
