"use client";

import type { Frontier, RuleProof } from "@/lib/types";

function Link({ href, label }: { href: string | null; label: string }) {
  if (!href) {
    return (
      <span className="rounded border border-dashed border-zinc-700 px-2 py-1 text-[11px] text-zinc-600">
        {label} — run scripts/prove_rule.py
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="rounded border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-[11px] text-violet-300 hover:bg-violet-500/20"
    >
      {label} ↗
    </a>
  );
}

export function EvidenceStrip({
  ruleProof,
  frontier,
}: {
  ruleProof: RuleProof | null;
  frontier: Frontier | null;
}) {
  const verdict = frontier?.verdict ?? [];
  return (
    <section className="flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-950/60 px-4 py-2.5">
      <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
        evidence
      </span>

      <Link href={ruleProof?.rule_off.trace_url ?? null} label="Logfire · rule off" />
      <Link href={ruleProof?.rule_on.trace_url ?? null} label="Logfire · rule on" />

      {ruleProof && (
        <span className="rounded bg-zinc-900 px-2 py-1 font-mono text-[11px] text-zinc-300">
          token delta {ruleProof.token_delta > 0 ? "+" : ""}
          {ruleProof.token_delta} ({ruleProof.token_delta_pct > 0 ? "+" : ""}
          {ruleProof.token_delta_pct}%)
        </span>
      )}

      <span className="ml-auto truncate text-[11px] text-zinc-500">
        {verdict[verdict.length - 1] ?? ""}
      </span>
    </section>
  );
}
