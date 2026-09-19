"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown, Rows3, Search } from "lucide-react";
import {
  BudgetTag,
  EmptyState,
  Panel,
  PanelHeader,
  RuleTag,
  VerdictTag,
} from "@/components/primitives";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtGpu, fmtTokens } from "@/lib/derive";
import { bareId, type TaskEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

type Key = "id" | "difficulty" | "stakes" | "budget" | "rule" | "tokens" | "gpu" | "verdict";

const COLUMNS: { key: Key; label: string; numeric?: boolean; className?: string }[] = [
  { key: "id", label: "Task" },
  { key: "difficulty", label: "Diff", numeric: true },
  { key: "stakes", label: "Stakes", numeric: true },
  { key: "budget", label: "Budget" },
  { key: "rule", label: "Rule" },
  { key: "tokens", label: "Tokens", numeric: true },
  { key: "gpu", label: "GPU", numeric: true },
  { key: "verdict", label: "Result" },
];

const valueOf = (e: TaskEvent, key: Key): string | number => {
  switch (key) {
    case "id":
      return bareId(e);
    case "difficulty":
      return e.difficulty;
    case "stakes":
      return e.stakes;
    case "budget":
      return e.budget;
    case "rule":
      return e.matched_rule ?? "";
    case "tokens":
      return e.total_tokens;
    case "gpu":
      return e.total_gpu_seconds;
    case "verdict":
      return e.correct === null ? 0 : e.correct ? 1 : -1;
  }
};

/** Every landed task, sortable and searchable. Clicking a row opens it in the console. */
export function TaskTable({
  events,
  selectedId,
  onSelect,
  ruleFilter,
  onClearRuleFilter,
}: {
  events: TaskEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  ruleFilter: string | null;
  onClearRuleFilter: () => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: Key; dir: "asc" | "desc" }>({
    key: "tokens",
    dir: "desc",
  });

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = events
      .filter((e) => {
        if (!ruleFilter) return true;
        if (ruleFilter.startsWith("—")) return !e.matched_rule;
        return e.matched_rule === ruleFilter;
      })
      .filter(
        (e) =>
          !q ||
          e.prompt_preview.toLowerCase().includes(q) ||
          bareId(e).toLowerCase().includes(q) ||
          (e.matched_rule ?? "").toLowerCase().includes(q)
      );

    const dir = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = valueOf(a, sort.key);
      const bv = valueOf(b, sort.key);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [events, query, ruleFilter, sort]);

  const toggle = (key: Key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));

  return (
    <Panel className="flex flex-col">
      <PanelHeader
        title="All tasks"
        description="Sort any column, search the prompts, click a row to open it"
        icon={Rows3}
      >
        {ruleFilter && (
          <button
            type="button"
            onClick={onClearRuleFilter}
            className="rounded-md bg-rule/12 px-2 py-0.5 font-mono text-[11px] text-rule hover:bg-rule/20"
          >
            {ruleFilter} ✕
          </button>
        )}
        <div className="relative w-52">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search prompts and rules"
            aria-label="Search tasks"
            className="h-8 pl-8"
          />
        </div>
      </PanelHeader>

      {rows.length === 0 ? (
        <EmptyState
          icon={Rows3}
          title="No tasks match"
          body="Clear the search or the rule filter to see the whole run."
        />
      ) : (
        <div className="max-h-[460px] overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-card">
              <TableRow>
                {COLUMNS.map((c) => {
                  const active = sort.key === c.key;
                  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
                  return (
                    <TableHead
                      key={c.key}
                      className={cn(c.numeric && "text-right", c.key === "id" && "w-[34%]")}
                    >
                      <button
                        type="button"
                        onClick={() => toggle(c.key)}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-sm hover:text-foreground",
                          c.numeric && "flex-row-reverse",
                          active && "text-foreground"
                        )}
                      >
                        {c.label}
                        <Icon
                          className={cn("size-3", active ? "opacity-100" : "opacity-40")}
                          aria-hidden
                        />
                      </button>
                    </TableHead>
                  );
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((e) => (
                <TableRow
                  key={e.id}
                  onClick={() => onSelect(e.id)}
                  aria-selected={selectedId === e.id}
                  className={cn(
                    "cursor-pointer",
                    selectedId === e.id && "bg-accent/60 hover:bg-accent/60"
                  )}
                >
                  <TableCell className="max-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="shrink-0 font-mono text-xs text-muted-foreground">
                        {bareId(e)}
                      </span>
                      <span className="truncate text-xs">{e.prompt_preview}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {e.difficulty.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    <span className={cn(e.stakes >= 0.66 && "text-stakes")}>
                      {e.stakes.toFixed(2)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <BudgetTag budget={e.budget} />
                  </TableCell>
                  <TableCell className="max-w-0">
                    {e.matched_rule ? (
                      <RuleTag rule={e.matched_rule} className="max-w-full truncate" />
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {fmtTokens(e.total_tokens)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs text-muted-foreground">
                    {fmtGpu(e.total_gpu_seconds)}
                  </TableCell>
                  <TableCell>
                    <VerdictTag correct={e.correct} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Panel>
  );
}
