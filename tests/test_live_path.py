"""The live path must at least BUILD, even when nobody has credentials.

This file exists because `agent/worker.py` imported `OpenAIModel` long after
pydantic-ai renamed it to `OpenAIChatModel`. Every test ran in stub mode, so the
whole Gateway branch was dead code that raised ImportError on first contact and
nothing noticed. These tests construct the live objects without making a network
call, so an SDK rename breaks CI instead of breaking the demo.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from agent import worker
from agent.settings import settings

# A syntactically valid key so gateway_provider's region parser is exercised too.
FAKE_KEY = "pylf_v2_eu_" + "0" * 32


@pytest.fixture(autouse=True)
def _fresh_agents(monkeypatch):
    """The agent caches are module-level; don't leak a fake-key agent into other tests."""
    monkeypatch.setattr(worker, "_agents", {})
    monkeypatch.setattr(worker, "_recompute", {})


def with_settings(monkeypatch, **overrides):
    """Settings is a frozen dataclass, so swap the module's reference for a copy."""
    monkeypatch.setattr(worker, "settings", replace(settings, **overrides))


def test_worker_agent_constructs(monkeypatch):
    with_settings(monkeypatch, gateway_api_key=FAKE_KEY)
    agent = worker._agent_for(settings.rule_deep)
    assert agent is not None
    assert worker._agent_for(settings.rule_deep) is agent, "agents should be cached per rule"


def test_verifier_agent_constructs(monkeypatch):
    with_settings(monkeypatch, gateway_api_key=FAKE_KEY)
    assert worker._recompute_agent() is not None


def test_hugging_face_repo_id_survives_intact(monkeypatch):
    """The model id contains a slash, and must NOT be parsed as `<route>/<model>`.

    Deriving the route by splitting on "/" sent `google/gemma-4-31B-it` to a route
    named `google`, which does not exist. Route and model are separate settings.
    """
    with_settings(monkeypatch, gateway_route="modal", gateway_model="google/gemma-4-31B-it")
    assert worker.gateway_route() == "modal"
    assert worker._model_name() == "google/gemma-4-31B-it"


def test_route_is_independent_of_the_model(monkeypatch):
    with_settings(monkeypatch, gateway_route="my-endpoint", gateway_model="Qwen/Qwen2.5-7B-Instruct")
    assert worker.gateway_route() == "my-endpoint"
    assert worker._model_name() == "Qwen/Qwen2.5-7B-Instruct"


def test_metadata_widening_accepts_modal_weight_versions():
    """Modal sends `metadata.weight_versions` as a LIST; the OpenAI schema says
    dict[str, str]. Unwidened, a successful call is discarded as a validation error."""
    worker._widen_modal_metadata()
    from openai.types.chat import ChatCompletion

    completion = ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": "hi"}}],
        "metadata": {"weight_versions": ["v1", "v2"]},
    })
    assert completion.metadata["weight_versions"] == ["v1", "v2"]


def test_call_settings_carries_the_rule_header():
    deep = worker.call_settings(settings.rule_deep)
    assert deep["extra_headers"]["X-Gateway-Rule"] == settings.rule_deep
    cheap = worker.call_settings(settings.rule_cheap)
    assert cheap["extra_headers"]["X-Gateway-Rule"] == settings.rule_cheap


def test_rule_header_can_be_renamed_or_disabled(monkeypatch):
    monkeypatch.setenv("GATEWAY_RULE_HEADER", "X-Custom")
    assert worker.rule_headers("r") == {"X-Custom": "r"}
    monkeypatch.setenv("GATEWAY_RULE_HEADER", "off")
    assert worker.rule_headers("r") == {}


def test_native_effort_is_high_on_deep_and_low_on_cheap():
    assert worker.effort_settings(settings.rule_deep)["openai_reasoning_effort"] == "high"
    assert worker.effort_settings(settings.rule_cheap)["openai_reasoning_effort"] == "low"
    assert worker.effort_settings(settings.rule_deep)["extra_body"]["chat_template_kwargs"]["enable_thinking"]


def test_native_effort_off_still_sends_the_rule(monkeypatch):
    """PONDER_NATIVE_EFFORT=0 drops the provider parameter, never our own actuator."""
    with_settings(monkeypatch, native_effort=False)
    ms = worker.call_settings(settings.rule_deep)
    assert "extra_headers" in ms
    assert "openai_reasoning_effort" not in ms


async def test_retry_keeps_the_rule_header_and_drops_only_the_effort():
    """A rejected effort parameter must not silently downgrade to an unruled call."""
    seen: list[dict | None] = []

    class FlakyAgent:
        async def run(self, prompt, model_settings=None):
            seen.append(model_settings)
            if model_settings and "openai_reasoning_effort" in model_settings:
                raise RuntimeError("400 unknown parameter: reasoning_effort")
            return "ok"

    ms = worker.call_settings(settings.rule_deep)
    assert await worker._run(FlakyAgent(), "p", ms) == "ok"
    assert len(seen) == 2, "should have retried exactly once"
    assert "openai_reasoning_effort" not in seen[1]
    assert seen[1]["extra_headers"]["X-Gateway-Rule"] == settings.rule_deep


async def test_header_only_failure_is_raised_not_swallowed():
    """If the endpoint rejects the RULE, that is a real error -- surface it."""
    class Broken:
        async def run(self, prompt, model_settings=None):
            raise RuntimeError("403 rule not found")

    with pytest.raises(RuntimeError):
        await worker._run(Broken(), "p", {"extra_headers": {"X-Gateway-Rule": "nope"}})


def test_route_is_the_effort_actuator(monkeypatch):
    """Effort is switched by asking for a different ROUTE, because a Gateway
    Optimization binds to a route rather than to a per-request header."""
    with_settings(monkeypatch, route_cheap="ponder-cheap", route_deep="ponder-deep")
    assert worker.gateway_route(settings.rule_cheap) == "ponder-cheap"
    assert worker.gateway_route(settings.rule_deep) == "ponder-deep"


def test_single_route_still_works_when_per_effort_routes_are_unset(monkeypatch):
    with_settings(monkeypatch, gateway_route="modal", route_cheap="", route_deep="")
    assert worker.gateway_route(settings.rule_cheap) == "modal"
    assert worker.gateway_route(settings.rule_deep) == "modal"
