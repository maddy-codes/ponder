"""The README's echo test: does a Gateway guardrail redact the request?

If a Redact/Block protection is installed on the route, the model never sees the
digits and echoes a placeholder. If nothing is installed, the digits come back.
"""
import asyncio, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from agent.settings import settings
from agent.worker import _gateway_model

PHONE = "07700 900123"          # Ofcom drama range, never a real subscriber
PROMPT = ("Repeat the following back to me character for character, with no other "
          f"words: my direct line is {PHONE}")

async def main():
    from pydantic_ai import Agent
    for rule in (settings.rule_cheap, settings.rule_deep):
        agent = Agent(_gateway_model(rule))
        try:
            r = await agent.run(PROMPT)
            out = str(r.output).strip()
        except Exception as e:
            out = f"<error: {str(e)[:160]}>"
        leaked = PHONE.replace(" ", "") in out.replace(" ", "")
        print(f"\nroute={settings.gateway_route}  rule={rule}")
        print(f"  MODEL RETURNED: {out[:200]!r}")
        print(f"  -> digits reached the model: {'YES (no gateway guardrail firing)' if leaked else 'NO (redacted/blocked)'}")

asyncio.run(main())
