import { isoOf } from "./export";
import { bareId, ruleOverrode, type TaskEvent } from "./types";

export type Receipt = {
  /** Stable for a given event: re-issuing the same exchange gives the same number. */
  number: string;
  /** Short digest of the canonical event record, so a receipt can be tied back to it. */
  fingerprint: string;
  fingerprintAlgorithm: "sha-256" | "fnv-1a (fallback)";
  issuedAt: string;
  event: TaskEvent;
};

/** Key-sorted JSON so the same record always hashes to the same digest. */
function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0
  );
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
}

const group = (hex: string) => hex.match(/.{1,4}/g)?.join(" ") ?? hex;

/** Non-crypto fallback for contexts where SubtleCrypto is unavailable (http://, old WebView). */
function fnv1a(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0").repeat(2).slice(0, 16);
}

export async function buildReceipt(event: TaskEvent, now = new Date()): Promise<Receipt> {
  const body = canonical(event);
  let fingerprint: string;
  let algorithm: Receipt["fingerprintAlgorithm"] = "sha-256";
  try {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
    fingerprint = [...new Uint8Array(digest)]
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")
      .slice(0, 16);
  } catch {
    fingerprint = fnv1a(body);
    algorithm = "fnv-1a (fallback)";
  }

  const d = new Date(event.ts * 1000);
  const p = (n: number) => `${n}`.padStart(2, "0");
  const day = `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}`;

  return {
    number: `PDR-${day}-${bareId(event).toUpperCase()}-${fingerprint.slice(0, 4).toUpperCase()}`,
    fingerprint: group(fingerprint),
    fingerprintAlgorithm: algorithm,
    issuedAt: now.toISOString(),
    event,
  };
}

/** A task still in flight can be receipted, but the document has to say so. */
export const isProvisional = (e: TaskEvent) => e.status !== "done";

export const ruleVerdict = (e: TaskEvent) =>
  !e.matched_rule
    ? "no named rule matched — the difficulty × stakes score decided"
    : ruleOverrode(e)
      ? "named rule overrode the score"
      : "named rule confirmed the score";

/**
 * What the guardrail layer did to this answer.
 *
 * An escalation is called out first because it is the part a reader would otherwise
 * miss: the compute on this receipt is higher than the rule alone asked for, and this
 * line is the reason why.
 */
export const guardrailOutcome = (e: TaskEvent) => {
  if (!e.guardrails?.length) return "no guardrails required by the matched rule";
  if (e.guardrail_blocked) {
    // No samples means nothing was ever spent, which only happens when an input-stage
    // guard refused the prompt. Worth saying outright: it is the difference between
    // "we paid for an answer and threw it away" and "the model was never asked".
    return e.samples?.length
      ? "BLOCKED — the answer was withheld"
      : "BLOCKED before any compute — the prompt was refused and no model call was made";
  }
  const failed = (e.guardrail_verdicts ?? []).filter((v) => v.outcome !== "allow");
  if (e.guardrail_escalated) {
    return failed.length
      ? `tripped, escalated to deep, and ${failed.map((v) => v.name).join(", ")} still failed`
      : "tripped on the cheap answer, escalated to deep, then all guardrails passed";
  }
  return failed.length
    ? `failed: ${failed.map((v) => v.name).join(", ")}`
    : "all guardrails passed";
};

export const sandboxOutcome = (e: TaskEvent) =>
  !e.sandbox_ran
    ? "not run"
    : e.sandbox_passed === true
      ? "executed — agreed with the answer"
      : e.sandbox_passed === false
        ? "executed — disagreed; the answer was replaced by the executed value"
        : "executed — inconclusive; the answer was kept and flagged";

export const gradeOutcome = (e: TaskEvent) =>
  e.correct === null
    ? "ungraded (no reference answer held for this task)"
    : e.correct
      ? "correct"
      : "miss";

/** The receipt as a plain-text document — what gets copied, saved as .md, or pasted into a ticket. */
export function receiptMarkdown(r: Receipt): string {
  const e = r.event;
  const L: string[] = [];
  const row = (k: string, v: string | number) => L.push(`| ${k} | ${v} |`);
  const head = () => L.push("", "| Field | Value |", "| --- | --- |");

  L.push(`# Ponder — Decision Receipt`, "");
  L.push(`**Receipt** \`${r.number}\``);
  L.push(`**Record fingerprint** \`${r.fingerprint}\` (${r.fingerprintAlgorithm})`);
  L.push(`**Issued** ${r.issuedAt}`);
  if (isProvisional(e))
    L.push(
      "",
      `> **PROVISIONAL** — this task had not finished when the receipt was issued ` +
        `(status: \`${e.status}\`). Re-issue once it lands for a final record.`
    );
  L.push("", "---", "");

  L.push("## Request", "", "> " + e.prompt_preview.replaceAll("\n", "\n> "));

  L.push("", "## Triage");
  head();
  row("Difficulty", e.difficulty.toFixed(2));
  row("Stakes", e.stakes.toFixed(2));

  L.push("", "## Policy");
  head();
  row("Matched rule", e.matched_rule ? `\`${e.matched_rule}\`` : "none");
  row("Verdict", ruleVerdict(e));
  row("Reason", e.rule_reason ?? "—");
  row("Gateway rule", `\`${e.rule_id}\``);

  L.push("", "## Compute committed");
  head();
  row("Budget", e.budget);
  row("Samples (best-of)", e.samples.length);
  row("Total tokens", e.total_tokens.toLocaleString("en-GB"));
  row("Total GPU seconds", e.total_gpu_seconds.toFixed(2));
  row("Latency", `${e.latency_ms} ms`);

  if (e.samples.length) {
    L.push("", "| # | Status | Tokens | GPU (s) |", "| --- | --- | --- | --- |");
    e.samples.forEach((s, i) =>
      L.push(`| ${i + 1} | ${s.status} | ${s.tokens} | ${s.gpu_seconds.toFixed(2)} |`)
    );
  }

  L.push("", "## Verification");
  head();
  row("Sandbox", sandboxOutcome(e));
  row("Guardrails required", e.guardrails?.length ? e.guardrails.map((g) => `\`${g}\``).join(", ") : "none");
  if (e.guardrail_verdicts?.length) {
    row("Guardrail outcome", guardrailOutcome(e));
    L.push("", "| Guardrail | Verdict | Detail |", "| --- | --- | --- |");
    e.guardrail_verdicts.forEach((v) =>
      L.push(`| \`${v.name}\` | ${v.outcome} | ${(v.detail || "—").replaceAll("|", "\\|")} |`)
    );
  }

  L.push("", "## Result");
  head();
  row("Answer", (e.answer ?? "—").replaceAll("|", "\\|").replaceAll("\n", " "));
  row("Grade", gradeOutcome(e));

  L.push("", "## Provenance");
  head();
  row("Event id", `\`${e.id}\``);
  row("Task", `\`${bareId(e)}\``);
  row("Strategy", e.strategy);
  row("Status", e.status);
  row("Emitted at", isoOf(e));
  row("Logfire trace", e.logfire_trace_url ?? "not captured for this run");
  row("Recording", "events.jsonl");

  L.push(
    "",
    "---",
    "",
    "Generated by Ponder Mission Control. Every value above is a field of the `TaskEvent`",
    "record this receipt fingerprints; nothing here is recomputed or inferred."
  );
  return L.join("\n") + "\n";
}

/** Machine-readable receipt: the envelope plus the untouched event record. */
export function receiptJson(r: Receipt): string {
  const e = r.event;
  return JSON.stringify(
    {
      document: "ponder.decision-receipt",
      version: 1,
      receipt_number: r.number,
      issued_at: r.issuedAt,
      provisional: isProvisional(e),
      record_fingerprint: r.fingerprint.replaceAll(" ", ""),
      fingerprint_algorithm: r.fingerprintAlgorithm,
      summary: {
        task: bareId(e),
        rule_verdict: ruleVerdict(e),
        sandbox: sandboxOutcome(e),
        guardrails: guardrailOutcome(e),
        grade: gradeOutcome(e),
      },
      event: e,
    },
    null,
    2
  );
}
