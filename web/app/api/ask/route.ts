import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const ROOT = path.join(process.cwd(), "..");
/** A deep task fans out N containers and then executes a sandbox; measured range is
 *  8-55s, so the old 90s ceiling was close enough to kill real work. */
const TIMEOUT_MS = 240_000;

/** The venv interpreter if it is there, otherwise let uv resolve one. */
function interpreter(): { cmd: string; args: string[] } {
  const venv = path.join(ROOT, ".venv", "bin", "python");
  if (existsSync(venv)) return { cmd: venv, args: [] };
  return { cmd: "uv", args: ["run", "python"] };
}

/**
 * Ponder one typed prompt, streaming each stage as it happens.
 *
 * This shells out to the same `agent.ask` entry point the README documents, which runs
 * the same `run_task` the batch queue runs. There is no second pipeline: the task
 * triages, matches rules, spends, verifies and emits its one TaskEvent to all three
 * sinks, so it lands in events.jsonl alongside the batch.
 *
 * `--stream` makes the agent print one NDJSON TaskEvent per real stage transition
 * (triage+budget decided, fan-out landed, verifying, done) and we forward those
 * verbatim. Nothing is synthesised here — a stage appears when the agent reached it,
 * which is the point: a 50-second deep task has to look like work, not like a hang.
 *
 * The response is NDJSON, one snapshot per line, and the line carrying `final: true`
 * is the durable TaskEvent. An error arrives as a line carrying `error`.
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
  const child = spawn(cmd, [...args, "-m", "agent.ask", prompt, "--stream"], {
    cwd: ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      let sawFinal = false;
      let buffer = "";
      const errChunks: string[] = [];

      const send = (obj: unknown) => {
        if (!closed) controller.enqueue(encoder.encode(`${JSON.stringify(obj)}\n`));
      };
      const finish = () => {
        if (closed) return;
        closed = true;
        controller.close();
      };

      const timer = setTimeout(() => {
        send({ error: `the agent took longer than ${TIMEOUT_MS / 1000}s` });
        child.kill("SIGKILL");
        finish();
      }, TIMEOUT_MS);

      child.stdout.on("data", (chunk: Buffer) => {
        buffer += chunk.toString();
        // Forward only whole lines; a split NDJSON line is not yet parseable.
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            if (event?.final) sawFinal = true;
            send(event);
          } catch {
            // The emitter is free to log above the stream; skip anything not NDJSON.
          }
        }
      });

      child.stderr.on("data", (chunk: Buffer) => {
        errChunks.push(chunk.toString());
      });

      child.on("error", (e) => {
        clearTimeout(timer);
        send({ error: `could not start the agent: ${e.message}` });
        finish();
      });

      child.on("close", (code) => {
        clearTimeout(timer);
        if (!sawFinal) {
          const stderr = errChunks.join("").trim();
          send({
            error: stderr.split("\n").slice(-3).join(" ") || `the agent exited with ${code}`,
          });
        }
        finish();
      });

      // The browser navigated away or the user cancelled: stop burning GPU for it.
      request.signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        child.kill("SIGKILL");
        finish();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-store, no-transform",
      // Without this a proxy can sit on the stream and hand it over in one piece,
      // which would put us right back where we started.
      "X-Accel-Buffering": "no",
    },
  });
}
