import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import type { TaskEvent } from "@/lib/types";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

const ROOT = path.join(process.cwd(), "..");
const TIMEOUT_MS = 90_000;

/** The venv interpreter if it is there, otherwise let uv resolve one. */
function interpreter(): { cmd: string; args: string[] } {
  const venv = path.join(ROOT, ".venv", "bin", "python");
  if (existsSync(venv)) return { cmd: venv, args: [] };
  return { cmd: "uv", args: ["run", "python"] };
}

/**
 * Ponder one typed prompt.
 *
 * This shells out to the same `agent.ask` entry point the README documents, which
 * runs the same `run_task` the batch queue runs. There is no second pipeline and no
 * special-casing: the task triages, matches rules, spends, verifies and emits its one
 * TaskEvent to all three sinks, so it lands in events.jsonl alongside the batch.
 */
export async function POST(request: Request) {
  let prompt = "";
  try {
    prompt = String((await request.json())?.prompt ?? "").trim();
  } catch {
    return NextResponse.json({ error: "expected a JSON body with a prompt" }, { status: 400 });
  }
  if (!prompt) return NextResponse.json({ error: "prompt is empty" }, { status: 400 });
  if (prompt.length > 2000) {
    return NextResponse.json({ error: "prompt is too long (2000 chars max)" }, { status: 400 });
  }

  const { cmd, args } = interpreter();
  // Argument array, never a shell string -- the prompt is user input.
  const child = spawn(cmd, [...args, "-m", "agent.ask", prompt, "--json"], {
    cwd: ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });

  const out: Buffer[] = [];
  const err: Buffer[] = [];
  child.stdout.on("data", (c) => out.push(c));
  child.stderr.on("data", (c) => err.push(c));

  const code: number | null = await new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      resolve(null);
    }, TIMEOUT_MS);
    child.on("error", () => {
      clearTimeout(timer);
      resolve(-1);
    });
    child.on("close", (c) => {
      clearTimeout(timer);
      resolve(c);
    });
  });

  const stderr = Buffer.concat(err).toString().trim();
  if (code === null) {
    return NextResponse.json({ error: `the agent took longer than ${TIMEOUT_MS / 1000}s` }, { status: 504 });
  }
  if (code !== 0) {
    return NextResponse.json(
      { error: stderr.split("\n").slice(-3).join(" ") || `agent exited with ${code}` },
      { status: 500 }
    );
  }

  // --json prints the TaskEvent and nothing else, but the emitter is free to log
  // above it, so take the last non-empty line.
  const lines = Buffer.concat(out).toString().split("\n").filter((l) => l.trim());
  try {
    const event: TaskEvent = JSON.parse(lines[lines.length - 1]);
    return NextResponse.json({ event });
  } catch {
    return NextResponse.json({ error: "the agent produced no TaskEvent" }, { status: 500 });
  }
}
