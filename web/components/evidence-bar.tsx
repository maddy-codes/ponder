"use client";

import { ExternalLink, FileSearch } from "lucide-react";
import { Panel, PanelHeader } from "@/components/primitives";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Frontier, RuleProof } from "@/lib/types";
import { cn } from "@/lib/utils";

function TraceLink({
  href,
  label,
  tokens,
}: {
  href: string | null;
  label: string;
  tokens?: number;
}) {
  if (!href) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <span className="flex cursor-default items-center gap-1.5 rounded-lg border border-dashed border-border px-2.5 py-1.5 text-xs text-muted-foreground">
              {label}
            </span>
          }
        />
        <TooltipContent>
          Run scripts/prove_rule.py with live credentials to capture this trace
        </TooltipContent>
      </Tooltip>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-1.5 rounded-lg border border-rule/30 bg-rule/8 px-2.5 py-1.5 text-xs text-rule transition-colors hover:bg-rule/16"
    >
      {label}
      {tokens !== undefined && <span className="font-mono opacity-70">{tokens}t</span>}
      <ExternalLink className="size-3" aria-hidden />
    </a>
  );
}

export function EvidenceBar({
  ruleProof,
  frontier,
}: {
  ruleProof: RuleProof | null;
  frontier: Frontier | null;
}) {
  const verdict = frontier?.verdict ?? [];
  const delta = ruleProof?.token_delta ?? 0;

  return (
    <Panel>
      <PanelHeader
        title="Evidence"
        description="The two traces and the measured token delta behind the claim"
        icon={FileSearch}
      />
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <TraceLink
          href={ruleProof?.rule_off.trace_url ?? null}
          label="Logfire · rule off"
          tokens={ruleProof?.rule_off.tokens}
        />
        <TraceLink
          href={ruleProof?.rule_on.trace_url ?? null}
          label="Logfire · rule on"
          tokens={ruleProof?.rule_on.tokens}
        />
        {ruleProof && (
          <span
            className={cn(
              "rounded-lg border border-border bg-muted/50 px-2.5 py-1.5 font-mono text-xs",
              delta > 0 ? "text-deep" : "text-ok"
            )}
          >
            {delta > 0 ? "+" : ""}
            {delta} tokens ({ruleProof.token_delta_pct > 0 ? "+" : ""}
            {ruleProof.token_delta_pct}%) from the rule
          </span>
        )}
        {verdict.length > 0 && (
          <p className="ml-auto max-w-lg text-right text-xs text-muted-foreground">
            {verdict[verdict.length - 1]}
          </p>
        )}
      </div>
    </Panel>
  );
}
