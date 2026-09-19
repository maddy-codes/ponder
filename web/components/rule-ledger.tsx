"use client";

import { Scale } from "lucide-react";
import { EmptyState, Panel, PanelHeader } from "@/components/primitives";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtGpu, fmtTokens, type RuleRow } from "@/lib/derive";
import { cn } from "@/lib/utils";

/**
 * The audit trail for "the policy chose this, not the classifier". One row per named
 * rule: how often it fired, what it forced, and what that cost.
 */
export function RuleLedger({
  rows,
  activeRule,
  onPick,
}: {
  rows: RuleRow[];
  activeRule: string | null;
  onPick: (rule: string | null) => void;
}) {
  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Rule ledger"
        description="Named domain rules, and the compute each one committed"
        icon={Scale}
      >
        {activeRule && (
          <button
            type="button"
            onClick={() => onPick(null)}
            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            Clear filter
          </button>
        )}
      </PanelHeader>

      {rows.length === 0 ? (
        <EmptyState icon={Scale} title="No rules have fired yet" />
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-card">
              <TableRow>
                <TableHead className="w-[38%]">Rule</TableHead>
                <TableHead className="text-right">Fired</TableHead>
                <TableHead className="text-right">Deep</TableHead>
                <TableHead className="text-right">Verified</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">GPU</TableHead>
                <TableHead className="text-right">Correct</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => {
                const named = !r.rule.startsWith("—");
                const active = activeRule === r.rule;
                return (
                  <TableRow
                    key={r.rule}
                    onClick={() => onPick(active ? null : r.rule)}
                    aria-selected={active}
                    className={cn(
                      "cursor-pointer",
                      active && "bg-accent/60 hover:bg-accent/60"
                    )}
                  >
                    <TableCell className="max-w-0">
                      <span
                        className={cn(
                          "block truncate font-mono text-xs",
                          named ? "text-rule" : "text-muted-foreground"
                        )}
                      >
                        {r.rule}
                      </span>
                      {r.overrides > 0 && (
                        <span className="text-[11px] text-muted-foreground">
                          {r.overrides} overrode the score
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{r.matches}</TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {r.deep ? <span className="text-deep">{r.deep}</span> : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {r.sandbox || "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {fmtTokens(r.tokens)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                      {fmtGpu(r.gpu)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {r.graded ? `${r.correct}/${r.graded}` : "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Panel>
  );
}
