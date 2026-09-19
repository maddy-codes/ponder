"use client";

import { useMemo, useState } from "react";
import { Radio, Search } from "lucide-react";
import { BudgetTag, Dot, EmptyState, Panel, PanelHeader, RuleTag } from "@/components/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { bareId, escalatedOnStakes, type TaskEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

type Filter = "all" | "deep" | "cheap" | "rule" | "miss";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "deep", label: "Deep" },
  { key: "cheap", label: "Cheap" },
  { key: "rule", label: "Rule" },
  { key: "miss", label: "Misses" },
];

const matches = (e: TaskEvent, f: Filter) =>
  f === "all"
    ? true
    : f === "rule"
      ? Boolean(e.matched_rule)
      : f === "miss"
        ? e.correct === false
        : e.budget === f;

export function QueueList({
  completed,
  current,
  total,
  selectedId,
  onSelect,
  following,
  onFollow,
}: {
  completed: TaskEvent[];
  current?: TaskEvent;
  total: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  following: boolean;
  onFollow: () => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...completed]
      .reverse()
      .filter((e) => matches(e, filter))
      .filter(
        (e) => !q || e.prompt_preview.toLowerCase().includes(q) || bareId(e).toLowerCase().includes(q)
      );
  }, [completed, filter, query]);

  return (
    <Panel className="flex h-full min-h-0 flex-col">
      <PanelHeader
        title="Queue"
        description={`${completed.length} of ${total} tasks landed`}
        icon={Radio}
      >
        {!following && (
          <Button variant="outline" size="xs" onClick={onFollow}>
            Follow live
          </Button>
        )}
      </PanelHeader>

      <div className="space-y-2 border-b border-border px-3 py-2.5">
        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks"
            aria-label="Search tasks"
            className="h-8 pl-8"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={cn(
                "rounded-md px-2 py-1 text-xs transition-colors",
                filter === f.key
                  ? "bg-secondary font-medium text-secondary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <ul className="divide-y divide-border">
          {current && matches(current, filter) && (
            <li>
              <Row
                event={current}
                live
                selected={following || selectedId === current.id}
                onSelect={onSelect}
              />
            </li>
          )}
          {rows.map((e) => (
            <li key={e.id}>
              <Row event={e} selected={!following && selectedId === e.id} onSelect={onSelect} />
            </li>
          ))}
          {rows.length === 0 && !current && (
            <li>
              <EmptyState
                icon={Search}
                title="Nothing matches"
                body="Clear the search or pick another filter."
              />
            </li>
          )}
        </ul>
      </ScrollArea>
    </Panel>
  );
}

function Row({
  event,
  selected,
  live,
  onSelect,
}: {
  event: TaskEvent;
  selected: boolean;
  live?: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(event.id)}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "rise w-full cursor-pointer px-3.5 py-2.5 text-left transition-colors",
        selected ? "bg-accent/60" : "hover:bg-muted/60",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:-outline-offset-2"
      )}
    >
      <div className="flex items-center gap-2">
        <Dot
          className={cn(
            "size-1.5",
            live
              ? "breathe bg-live"
              : event.correct === null
                ? "bg-muted-foreground/60"
                : event.correct
                  ? "bg-ok"
                  : "bg-miss"
          )}
        />
        <span className={cn("font-mono text-xs", live ? "text-live" : "text-muted-foreground")}>
          {bareId(event)}
        </span>
        {live && <span className="text-[11px] text-live">running</span>}
        <span className="ml-auto flex items-center gap-1">
          {event.matched_rule ? (
            <RuleTag rule={event.matched_rule} />
          ) : (
            escalatedOnStakes(event) && (
              <span className="rounded-md bg-stakes/12 px-1.5 py-0.5 text-[11px] font-medium text-stakes">
                stakes
              </span>
            )
          )}
          <BudgetTag budget={event.budget} />
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-foreground/85">
        {event.prompt_preview}
      </p>
    </button>
  );
}
