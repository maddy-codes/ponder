import json

from agent.events import Emitter, Sample, TaskEvent, load_events


def test_roll_up_sums_samples():
    e = TaskEvent(id="t", prompt_preview="p", samples=[
        Sample(status="done", tokens=10, gpu_seconds=0.5),
        Sample(status="done", tokens=7, gpu_seconds=0.25),
    ])
    e.roll_up()
    assert e.total_tokens == 17 and e.total_gpu_seconds == 0.75


def test_emit_writes_exactly_one_jsonl_line(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    import agent.events as mod

    monkeypatch.setattr(mod, "EVENTS_PATH", path)
    emitter = Emitter()
    monkeypatch.setattr(emitter.jsonl, "write", lambda ev: path.open("a").write(ev.model_dump_json() + "\n"))

    event = TaskEvent(id="t1", prompt_preview="p", samples=[Sample(status="done", tokens=3)])
    emitter.progress(event)   # progress must not touch the durable sinks
    emitter.progress(event)
    emitter.emit(event)

    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "t1"


def test_contract_round_trips(tmp_path):
    path = tmp_path / "e.jsonl"
    event = TaskEvent(id="x", prompt_preview="p", budget="deep", stakes=0.9)
    path.write_text(event.model_dump_json() + "\n")
    assert load_events(path)[0].budget == "deep"
