"""Executed verification.

One interface, two backends: a Modal Sandbox when Modal is live (this is the
`modal.Sandbox` use the Modal prize asks for) and a local subprocess otherwise,
so the deep path still verifies with no credentials.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agent.settings import settings

TIMEOUT_S = 20


@dataclass
class ExecResult:
    passed: bool
    stdout: str
    stderr: str
    backend: str

    @property
    def summary(self) -> str:
        detail = (self.stderr or self.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else ""
        return f"[{self.backend}] {'pass' if self.passed else 'fail'} {tail}"[:200]


def build_program(code: str, checks: list[str]) -> str:
    body = "\n".join(checks) if checks else "pass"
    return f"{code}\n\n# --- checks ---\n{body}\nprint('CHECKS_PASSED')\n"


def _run_local(program: str) -> ExecResult:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "candidate.py"
        script.write_text(program, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(False, "", f"timed out after {TIMEOUT_S}s", "local")
    return ExecResult("CHECKS_PASSED" in proc.stdout, proc.stdout, proc.stderr, "local")


def _run_modal(program: str) -> ExecResult:
    from agent.modal_app import run_in_sandbox

    return run_in_sandbox(program)


def execute(code: str, checks: list[str]) -> ExecResult:
    """Run `code` against `checks`, in a Modal Sandbox when available."""
    program = build_program(code, checks)
    if settings.use_modal:
        try:
            return _run_modal(program)
        except Exception as exc:  # pragma: no cover - falls back rather than failing the task
            print(f"[sandbox] modal unavailable, falling back to local: {exc}")
    return _run_local(program)
