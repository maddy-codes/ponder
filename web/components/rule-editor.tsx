"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Check,
  FlaskConical,
  Loader2,
  Plus,
  ScrollText,
  Trash2,
} from "lucide-react";
import { EmptyState, Panel, PanelHeader, RuleTag } from "@/components/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export type GuardSpec = { name: string; outcome: string; description: string };

export type AuthoredRule = {
  name: string;
  enabled: boolean;
  when: { phrases: string[]; requires_digit: boolean };
  then: { budget: "cheap" | "deep"; sandbox_verify: boolean; guardrails: string[] };
  reason: string;
};

type MatchResult = {
  prompt: string;
  matched: string | null;
  budget: string | null;
  sandbox_verify: boolean;
  guardrails: string[];
  reason: string | null;
};

const FIELD =
  "w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs " +
  "outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50";

function blankRule(n: number): AuthoredRule {
  return {
    name: `new_rule_${n}`,
    enabled: true,
    when: { phrases: [], requires_digit: false },
    then: { budget: "deep", sandbox_verify: false, guardrails: [] },
    reason: "",
  };
}

/**
 * Author the domain policy from the application.
 *
 * The rules are not in the code: `agent/rules.json` is the policy, this panel is its
 * editor, and `agent/rules.py` only loads and compiles it. That is the point of the
 * whole layer — the person who knows that a dose must be recomputed is not the person
 * who can ship a Python change, and here they do not have to be.
 *
 * Nothing here interprets the file itself. It reads what `agent.rules` reports as in
 * force and writes back through the same loader, so what you see is what the next task
 * will actually be judged by. The test box dry-runs a prompt against the live policy
 * with no model call at all: rule authoring is instant and free, and only the tasks
 * that follow cost anything.
 */
export function RuleEditor() {
  const [rules, setRules] = useState<AuthoredRule[]>([]);
  const [guards, setGuards] = useState<GuardSpec[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string>();
  const [savedAt, setSavedAt] = useState<number>();

  const [probe, setProbe] = useState("");
  const [probing, setProbing] = useState(false);
  const [hit, setHit] = useState<MatchResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/rules");
      const body = await res.json();
      if (body.error) setError(String(body.error));
      else setError(undefined);
      setRules(body.rules ?? []);
      setGuards(body.guardrails_available ?? []);
      setDirty(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const mutate = useCallback((fn: (draft: AuthoredRule[]) => AuthoredRule[]) => {
    setRules((current) => fn(current.map((r) => structuredClone(r))));
    setDirty(true);
    setSavedAt(undefined);
  }, []);

  const patch = useCallback(
    (index: number, fn: (rule: AuthoredRule) => void) =>
      mutate((draft) => {
        fn(draft[index]);
        return draft;
      }),
    [mutate]
  );

  const move = useCallback(
    (index: number, by: number) =>
      mutate((draft) => {
        const to = index + by;
        if (to < 0 || to >= draft.length) return draft;
        [draft[index], draft[to]] = [draft[to], draft[index]];
        return draft;
      }),
    [mutate]
  );

  const save = useCallback(async () => {
    setSaving(true);
    setError(undefined);
    try {
      const res = await fetch("/api/rules", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rules }),
      });
      const body = await res.json();
      if (!res.ok || body.error) {
        setError(String(body.error ?? `save failed (${res.status})`));
        return;
      }
      setRules(body.rules ?? rules);
      setDirty(false);
      setSavedAt(Date.now());
      if (probe.trim()) void runProbe();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
    // runProbe is stable enough for this one re-check; including it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rules, probe]);

  const runProbe = useCallback(async () => {
    const prompt = probe.trim();
    if (!prompt) {
      setHit(null);
      return;
    }
    setProbing(true);
    try {
      const res = await fetch("/api/rules", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const body = await res.json();
      setHit(body.error ? null : body);
      if (body.error) setError(String(body.error));
    } catch (e) {
      setError(String(e));
    } finally {
      setProbing(false);
    }
  }, [probe]);

  const guardsByName = useMemo(
    () => new Map(guards.map((g) => [g.name, g] as const)),
    [guards]
  );

  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Domain policy"
        description="The rules are data, not code — edit them here and the next task obeys"
        icon={ScrollText}
      >
        <div className="flex items-center gap-2">
          {savedAt && !dirty && (
            <span className="flex items-center gap-1 text-xs text-ok">
              <Check className="size-3.5" /> in force
            </span>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => mutate((d) => [...d, blankRule(d.length + 1)])}
          >
            <Plus className="size-3.5" /> Rule
          </Button>
          <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {saving ? "Saving" : dirty ? "Save policy" : "Saved"}
          </Button>
        </div>
      </PanelHeader>

      {error && (
        <p className="mx-4 mb-3 rounded-md bg-miss/10 px-3 py-2 text-xs text-miss">{error}</p>
      )}

      {/* ── dry run ─────────────────────────────────────────────────── */}
      <div className="mx-4 mb-4 rounded-lg border border-dashed p-3">
        <div className="flex items-center gap-2">
          <FlaskConical className="size-4 shrink-0 text-muted-foreground" />
          <Input
            value={probe}
            onChange={(e) => setProbe(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void runProbe()}
            placeholder="Try a prompt against the live policy — no model call, no tokens"
            className="h-8"
          />
          <Button size="sm" variant="secondary" disabled={probing} onClick={() => void runProbe()}>
            {probing ? <Loader2 className="size-3.5 animate-spin" /> : "Test"}
          </Button>
        </div>
        {hit && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
            {hit.matched ? (
              <>
                <RuleTag rule={hit.matched} />
                <span className="text-muted-foreground">forces</span>
                <Badge variant="outline" className={hit.budget === "deep" ? "text-deep" : "text-cheap"}>
                  {hit.budget}
                </Badge>
                {hit.sandbox_verify && <Badge variant="outline">sandbox verify</Badge>}
                {hit.guardrails.map((g) => (
                  <Badge key={g} variant="secondary" className="font-mono text-[10px]">
                    {g}
                  </Badge>
                ))}
              </>
            ) : (
              <span className="text-muted-foreground">
                No rule matches — difficulty × stakes decides this one on its own.
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── the rules ───────────────────────────────────────────────── */}
      <div className="flex-1 space-y-3 overflow-y-auto px-4 pb-4">
        {loading ? (
          <EmptyState icon={Loader2} title="Reading the policy…" />
        ) : rules.length === 0 ? (
          <EmptyState
            icon={ScrollText}
            title="No rules"
            body="With no policy, difficulty × stakes decides every task on its own."
          />
        ) : (
          rules.map((rule, i) => (
            <div
              key={`${rule.name}-${i}`}
              className={cn(
                "rounded-lg border p-3 transition",
                !rule.enabled && "opacity-55",
                hit?.matched === rule.name && "border-rule ring-1 ring-rule/30"
              )}
            >
              <div className="flex items-center gap-2">
                <span className="w-5 shrink-0 text-center font-mono text-[11px] text-muted-foreground">
                  {i + 1}
                </span>
                <Input
                  value={rule.name}
                  onChange={(e) =>
                    patch(i, (r) => {
                      r.name = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_");
                    })
                  }
                  className="h-8 max-w-56 font-mono text-xs"
                />
                <div className="ml-auto flex items-center gap-1">
                  <Button size="icon" variant="ghost" className="size-7" onClick={() => move(i, -1)}>
                    <ArrowUp className="size-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="size-7" onClick={() => move(i, 1)}>
                    <ArrowDown className="size-3.5" />
                  </Button>
                  <Switch
                    checked={rule.enabled}
                    onCheckedChange={(v) => patch(i, (r) => { r.enabled = v; })}
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-7 text-muted-foreground hover:text-miss"
                    onClick={() => mutate((d) => d.filter((_, j) => j !== i))}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {/* when */}
                <div className="space-y-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    When the prompt contains
                  </p>
                  <textarea
                    rows={3}
                    className={cn(FIELD, "font-mono text-xs")}
                    value={rule.when.phrases.join(", ")}
                    onChange={(e) =>
                      patch(i, (r) => {
                        r.when.phrases = e.target.value
                          .split(",")
                          .map((p) => p.trim().toLowerCase())
                          .filter(Boolean);
                      })
                    }
                    placeholder="mg/kg, dose, infusion"
                  />
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Switch
                      checked={rule.when.requires_digit}
                      onCheckedChange={(v) => patch(i, (r) => { r.when.requires_digit = v; })}
                    />
                    …and a figure is present
                  </label>
                </div>

                {/* then */}
                <div className="space-y-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Then spend
                  </p>
                  <div className="flex items-center gap-2">
                    {(["cheap", "deep"] as const).map((b) => (
                      <button
                        key={b}
                        type="button"
                        onClick={() => patch(i, (r) => { r.then.budget = b; })}
                        className={cn(
                          "rounded-md border px-2.5 py-1 text-xs capitalize transition",
                          rule.then.budget === b
                            ? b === "deep"
                              ? "border-deep bg-deep/12 text-deep"
                              : "border-cheap bg-cheap/12 text-cheap"
                            : "text-muted-foreground hover:bg-muted"
                        )}
                      >
                        {b}
                      </button>
                    ))}
                    <label className="ml-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <Switch
                        checked={rule.then.sandbox_verify}
                        onCheckedChange={(v) => patch(i, (r) => { r.then.sandbox_verify = v; })}
                      />
                      execute to verify
                    </label>
                  </div>

                  <p className="pt-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    …and the answer must clear
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {guards.map((g) => {
                      const on = rule.then.guardrails.includes(g.name);
                      return (
                        <button
                          key={g.name}
                          type="button"
                          title={`${g.description} (a failure will ${g.outcome})`}
                          onClick={() =>
                            patch(i, (r) => {
                              r.then.guardrails = on
                                ? r.then.guardrails.filter((n) => n !== g.name)
                                : [...r.then.guardrails, g.name];
                            })
                          }
                          className={cn(
                            "rounded-md border px-2 py-0.5 font-mono text-[10px] transition",
                            on
                              ? "border-rule bg-rule/12 text-rule"
                              : "text-muted-foreground hover:bg-muted"
                          )}
                        >
                          {g.name}
                        </button>
                      );
                    })}
                  </div>
                  {rule.then.budget === "cheap" && rule.then.guardrails.length > 0 && (
                    <p className="text-[11px] leading-snug text-muted-foreground">
                      Starts cheap. If a guardrail trips, the task escalates to deep and re-runs
                      rather than returning an unusable answer.
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-3">
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Because — this reason is the audit trail
                </p>
                <textarea
                  rows={2}
                  className={cn(FIELD, "text-xs")}
                  value={rule.reason}
                  onChange={(e) => patch(i, (r) => { r.reason = e.target.value; })}
                  placeholder="Why this policy exists, in the words of whoever owns the domain."
                />
              </div>

              {rule.then.guardrails.length > 0 && (
                <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                  {rule.then.guardrails
                    .map((n) => guardsByName.get(n)?.description)
                    .filter(Boolean)
                    .join(" ")}
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
