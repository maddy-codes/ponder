import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import type { TaskEvent } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Streams the recorded run. events.jsonl is the Replay file -- the demo does not
 *  depend on a live model call. */
export async function GET() {
  const file = path.join(process.cwd(), "..", "events.jsonl");
  let raw = "";
  try {
    raw = await readFile(file, "utf8");
  } catch {
    return NextResponse.json({ events: [], error: "events.jsonl not found -- run the agent first" });
  }
  const events: TaskEvent[] = raw
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l));

  // Later lines win: the emitter upserts by id, and so do we.
  const latest = new Map<string, TaskEvent>();
  for (const e of events) latest.set(e.id, e);
  return NextResponse.json({ events: [...latest.values()].sort((a, b) => a.ts - b.ts) });
}
