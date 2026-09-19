import { bareId, type TaskEvent } from "./types";

/** Browser-side save. Everything exported is already in the client -- no new backend. */
export function download(filename: string, mime: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  // Revoke on the next tick so Safari has taken the blob.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Filename stamp: 20260919-142233, local time, sortable. */
export function stamp(d = new Date()) {
  const p = (n: number) => `${n}`.padStart(2, "0");
  return (
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
  );
}

export const isoOf = (event: TaskEvent) => new Date(event.ts * 1000).toISOString();

/**
 * One flat row per task. The columns are the audit-relevant fields of TaskEvent,
 * in the order an auditor reads them: what was asked, how it was scored, what
 * policy decided, what that cost, whether it was verified, and what came out.
 */
const COLUMNS: { header: string; get: (e: TaskEvent) => string | number | boolean | null }[] = [
  { header: "event_id", get: (e) => e.id },
  { header: "task", get: (e) => bareId(e) },
  { header: "emitted_at", get: isoOf },
  { header: "strategy", get: (e) => e.strategy },
  { header: "prompt", get: (e) => e.prompt_preview },
  { header: "difficulty", get: (e) => e.difficulty },
  { header: "stakes", get: (e) => e.stakes },
  { header: "budget", get: (e) => e.budget },
  { header: "matched_rule", get: (e) => e.matched_rule },
  { header: "rule_reason", get: (e) => e.rule_reason },
  { header: "gateway_rule_id", get: (e) => e.rule_id },
  { header: "samples", get: (e) => e.samples.length },
  { header: "sample_statuses", get: (e) => e.samples.map((s) => s.status).join("|") },
  { header: "total_tokens", get: (e) => e.total_tokens },
  { header: "total_gpu_seconds", get: (e) => e.total_gpu_seconds },
  { header: "latency_ms", get: (e) => e.latency_ms },
  { header: "sandbox_ran", get: (e) => e.sandbox_ran },
  { header: "sandbox_passed", get: (e) => e.sandbox_passed },
  { header: "answer", get: (e) => e.answer },
  { header: "correct", get: (e) => e.correct },
  { header: "logfire_trace_url", get: (e) => e.logfire_trace_url },
];

const csvCell = (v: string | number | boolean | null) => {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
};

export function toCsv(events: TaskEvent[]): string {
  const rows = [COLUMNS.map((c) => c.header).join(",")];
  for (const e of events) rows.push(COLUMNS.map((c) => csvCell(c.get(e))).join(","));
  // BOM so Excel opens the UTF-8 prompts correctly.
  return `﻿${rows.join("\r\n")}\r\n`;
}

/** Pretty JSON with a small envelope, so an exported file says what it is. */
export function toJson(events: TaskEvent[], note: string): string {
  return JSON.stringify(
    {
      source: "Ponder Mission Control",
      exported_at: new Date().toISOString(),
      selection: note,
      count: events.length,
      events,
    },
    null,
    2
  );
}

/** Verbatim events.jsonl format — one TaskEvent per line, no envelope. */
export function toJsonl(events: TaskEvent[]): string {
  return events.map((e) => JSON.stringify(e)).join("\n") + "\n";
}
