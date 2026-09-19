import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const ROOT = path.join(process.cwd(), "..");
const RULES_PATH = path.join(ROOT, "agent", "rules.json");

/** The venv interpreter if it is there, otherwise let uv resolve one. */
function interpreter(): { cmd: string; args: string[] } {
  const venv = path.join(ROOT, ".venv", "bin", "python");
  if (existsSync(venv)) return { cmd: venv, args: [] };
  return { cmd: "uv", args: ["run", "python"] };
}

/**
 * Ask the agent what policy is actually in force.
 *
 * The editor deliberately does not read or write rules.json through its own parser.
 * It asks `agent.rules`, which is the same loader the loop runs, so what the editor
 * shows is provably what the next task will be judged by -- not a second
 * interpretation of the same file that can drift from it.
 */
function agentRules(extra: string[] = []): Promise<unknown> {
  const { cmd, args } = interpreter();
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, [...args, "-m", "agent.rules", ...extra], { cwd: ROOT });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", reject);
    const timer = setTimeout(() => child.kill(), 20_000);
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error(err.slice(0, 400) || `exit ${code}`));
      try {
        resolve(JSON.parse(out));
      } catch {
        reject(new Error("agent.rules did not return JSON"));
      }
    });
  });
}

export async function GET() {
  try {
    return NextResponse.json(await agentRules(["--json"]));
  } catch (e) {
    return NextResponse.json({ error: String(e), rules: [], guardrails_available: [] }, { status: 500 });
  }
}

type AuthoredRule = {
  name: string;
  enabled: boolean;
  when: { phrases: string[]; requires_digit: boolean };
  then: { budget: string; sandbox_verify: boolean; guardrails: string[] };
  reason: string;
};

const NAME = /^[a-z0-9_]{2,40}$/;

/**
 * Validate before writing, because this file is the running policy.
 *
 * `agent/rules.py` skips a malformed rule rather than crashing, but a rule that is
 * silently dropped is worse than one that is refused: the author believes a policy is
 * in force when it is not. So the failure is surfaced here, at the point of authorship.
 */
function validate(body: unknown): { rules: AuthoredRule[] } | { error: string } {
  const raw = (body as { rules?: unknown })?.rules;
  if (!Array.isArray(raw)) return { error: "expected { rules: [...] }" };
  if (raw.length > 50) return { error: "too many rules (50 max)" };

  const seen = new Set<string>();
  const rules: AuthoredRule[] = [];
  for (const [i, item] of raw.entries()) {
    const r = item as Partial<AuthoredRule>;
    const name = String(r?.name ?? "").trim();
    if (!NAME.test(name)) {
      return { error: `rule ${i + 1}: name must be lower_snake_case (got "${name}")` };
    }
    if (seen.has(name)) return { error: `duplicate rule name "${name}"` };
    seen.add(name);

    const phrases = (r?.when?.phrases ?? [])
      .map((p) => String(p).toLowerCase().trim())
      .filter(Boolean);
    if (phrases.length === 0) {
      return { error: `rule "${name}": needs at least one trigger phrase` };
    }
    const budget = String(r?.then?.budget ?? "");
    if (budget !== "cheap" && budget !== "deep") {
      return { error: `rule "${name}": budget must be "cheap" or "deep"` };
    }
    const reason = String(r?.reason ?? "").trim();
    if (!reason) {
      return { error: `rule "${name}": needs a reason — it is the audit trail` };
    }
    rules.push({
      name,
      enabled: Boolean(r?.enabled ?? true),
      when: { phrases, requires_digit: Boolean(r?.when?.requires_digit) },
      then: {
        budget,
        sandbox_verify: Boolean(r?.then?.sandbox_verify),
        guardrails: (r?.then?.guardrails ?? []).map((g) => String(g)),
      },
      reason,
    });
  }
  return { rules };
}

export async function PUT(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "expected a JSON body" }, { status: 400 });
  }

  const checked = validate(body);
  if ("error" in checked) return NextResponse.json(checked, { status: 400 });

  const doc = {
    version: 1,
    note: "Authored policy. Edited in Mission Control (Rules tab) or by hand; agent/rules.py only loads and compiles it. Order is precedence: the first enabled rule whose `when` fires decides, so escalating rules come first.",
    rules: checked.rules,
  };

  try {
    // Write-then-rename: the agent may be mid-run and reloads this file on mtime, so it
    // must never observe a half-written policy.
    const tmp = `${RULES_PATH}.${process.pid}.tmp`;
    await writeFile(tmp, `${JSON.stringify(doc, null, 2)}\n`, "utf8");
    await rename(tmp, RULES_PATH);
  } catch (e) {
    return NextResponse.json({ error: `could not write policy: ${e}` }, { status: 500 });
  }

  // Echo back what the agent now reports, so the editor shows the compiled truth
  // rather than the text it just typed.
  try {
    return NextResponse.json({ saved: true, ...(await agentRules(["--json"]) as object) });
  } catch {
    return NextResponse.json({ saved: true, rules: checked.rules });
  }
}

/** Dry-run one prompt against the live policy. No model call, no tokens. */
export async function POST(request: Request) {
  let prompt = "";
  try {
    prompt = String(((await request.json()) as { prompt?: unknown })?.prompt ?? "").trim();
  } catch {
    return NextResponse.json({ error: "expected a JSON body with a prompt" }, { status: 400 });
  }
  if (!prompt) return NextResponse.json({ error: "prompt is empty" }, { status: 400 });
  if (prompt.length > 2000) return NextResponse.json({ error: "prompt too long" }, { status: 400 });

  try {
    return NextResponse.json(await agentRules(["--match", prompt]));
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
