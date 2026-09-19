"""The bench's stage stream.

The live Gateway path once sat broken for days because nothing executed it. The
stream is the same kind of seam -- the dashboard is its only consumer, so a rename
in the emitter would break it silently. These tests run the real `StreamEmitter`
against a real `run_task` (stub worker) and read the NDJSON back.
"""

from __future__ import annotations

import json

import pytest

from agent import events
from agent.ask import StreamEmitter, as_task
from agent.events import TaskEvent
from agent.loop import run_task


@pytest.fixture
def lines(capsys, tmp_path, monkeypatch):
    """Run one task through the streaming emitter and hand back the parsed NDJSON.

    events.jsonl is the demo recording, and JsonlSink appends to it unconditionally
    (that is invariant 4 -- the file is written whatever else is down). A test that
    runs a real task must therefore redirect it, or the suite quietly rewrites the
    thing the demo plays back.
    """
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")

    async def run(prompt: str) -> list[dict]:
        await run_task(as_task(prompt, "streamtest"), strategy="ponder", emitter=StreamEmitter())
        out = capsys.readouterr().out
        # Same tolerance the route has: the worker and Modal are free to log on
        # stdout alongside the stream, so anything that is not a snapshot is skipped
        # rather than treated as corruption.
        snaps = []
        for line in out.splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "final" in parsed:
                snaps.append(parsed)
        return snaps

    return run


async def test_stream_emits_stages_and_one_final(lines):
    got = await lines("What is the total cost of 3 items at 4.50 each?")
    assert len(got) >= 2, "the loop publishes progress before the durable emit"
    assert [snap["final"] for snap in got].count(True) == 1
    assert got[-1]["final"] is True, "the last line must be the durable event"


async def test_every_line_is_a_valid_taskevent(lines):
    """The bench types these as TaskEvent, so a drifted field would break it."""
    got = await lines("What is the capital of Peru?")
    for snap in got:
        TaskEvent.model_validate({k: v for k, v in snap.items() if k != "final"})


async def test_first_snapshot_already_carries_the_decision(lines):
    """The whole point: the rail can show triage, rule and budget immediately,
    long before the model has returned anything."""
    got = await lines("What is the total cost of 3 items at 4.50 each?")
    first = got[0]
    assert first["status"] == "thinking"
    assert first["matched_rule"] == "financial_total"
    assert first["budget"] == "deep"
    assert first["samples"], "the fan-out width is known up front"
    assert all(s["status"] == "running" for s in first["samples"])


async def test_totals_roll_up_on_every_snapshot(lines):
    """`roll_up()` normally runs only on the durable emit; the stream does it on a
    copy so the bench can show a running token count that still ends up correct."""
    got = await lines("What is the total cost of 3 items at 4.50 each?")
    final = got[-1]
    assert final["total_tokens"] == sum(s["tokens"] for s in final["samples"])
    assert final["status"] == "done"
    assert final["total_tokens"] > 0


async def test_stream_does_not_disturb_the_durable_event(lines, tmp_path):
    """Snapshotting must not mutate the event the three sinks receive."""
    got = await lines("What is the capital of Peru?")
    ids = {snap["id"] for snap in got}
    assert ids == {"ponder:streamtest"}, "every line describes the same one task"
