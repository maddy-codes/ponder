"""One resolved config object. Nothing else in the codebase reads os.environ."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EVENTS_PATH = ROOT / "events.jsonl"
TASKS_PATH = ROOT / "agent" / "tasks.jsonl"
ARTIFACTS = ROOT / "artifacts"


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


@dataclass(frozen=True)
class Settings:
    """Resolved once at import. Each sink decides for itself whether it can run."""

    mode: str = field(default_factory=lambda: _env("PONDER_MODE", "stub").lower())

    logfire_token: str = field(default_factory=lambda: _env("LOGFIRE_TOKEN"))
    logfire_project_url: str = field(default_factory=lambda: _env("LOGFIRE_PROJECT_URL"))
    gateway_api_key: str = field(default_factory=lambda: _env("PYDANTIC_AI_GATEWAY_API_KEY"))
    gateway_base_url: str = field(
        default_factory=lambda: _env("PYDANTIC_AI_GATEWAY_BASE_URL", "https://gateway.pydantic.dev/v1")
    )
    # The BYOK provider name you created in the Gateway console. Separate from the
    # model: a Hugging Face repo id contains a slash, so it cannot be split apart.
    gateway_route: str = field(default_factory=lambda: _env("GATEWAY_ROUTE", "modal"))
    # A Gateway Optimization binds to a ROUTE, not to a per-request header, so effort is
    # switched by pointing at a different BYOK provider. Both providers front the SAME
    # Modal endpoint; only the optimization installed on each differs. Blank = one route
    # for both, and the effort difference falls back to the system prompt alone.
    route_cheap: str = field(default_factory=lambda: _env("GATEWAY_ROUTE_CHEAP"))
    route_deep: str = field(default_factory=lambda: _env("GATEWAY_ROUTE_DEEP"))
    # The Hugging Face repo id served by that endpoint, used verbatim.
    gateway_model: str = field(default_factory=lambda: _env("GATEWAY_MODEL"))
    rule_cheap: str = field(default_factory=lambda: _env("GATEWAY_RULE_CHEAP", "ponder-cheap-answer-only"))
    rule_deep: str = field(default_factory=lambda: _env("GATEWAY_RULE_DEEP", "ponder-deep-reason"))

    # Best-effort: also set the worker model's OWN reasoning control on the deep
    # path, not just ours. Turn off if the served model rejects the parameter.
    native_effort: bool = field(default_factory=lambda: _env("PONDER_NATIVE_EFFORT", "1") not in {"0", "off", "false"})

    modal_token_id: str = field(default_factory=lambda: _env("MODAL_TOKEN_ID"))
    model_endpoint_url: str = field(default_factory=lambda: _env("MODEL_ENDPOINT_URL"))

    convex_url: str = field(default_factory=lambda: _env("CONVEX_URL") or _env("NEXT_PUBLIC_CONVEX_URL"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    # Pinned in env, not in code: Google retires judge models faster than we rebuild.
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-3.6-flash"))

    # --- effort dials -------------------------------------------------
    deep_samples: int = 5          # best-of-N width on the deep path
    stakes_override: float = 0.66  # above this, escalate regardless of difficulty
    difficulty_deep: float = 0.55  # above this, escalate on difficulty alone
    sandbox_stakes: float = 0.75   # above this, execute-verify the answer
    max_concurrency: int = 6

    @property
    def live(self) -> bool:
        """True when the worker model should be a real Gateway -> Modal call."""
        return self.mode == "live" and bool(self.gateway_api_key)

    @property
    def use_logfire(self) -> bool:
        return bool(self.logfire_token)

    @property
    def use_convex(self) -> bool:
        return bool(self.convex_url)

    @property
    def use_modal(self) -> bool:
        return self.mode == "live" and bool(self.modal_token_id)

    def describe(self) -> str:
        def mark(ok: bool) -> str:
            return "on " if ok else "off"

        return (
            f"mode={self.mode} worker={'gateway->modal' if self.live else 'stub'} "
            f"logfire={mark(self.use_logfire)} convex={mark(self.use_convex)} "
            f"modal={mark(self.use_modal)} jsonl=on"
        )


settings = Settings()
