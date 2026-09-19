"use client";

import Image from "next/image";
import { Pause, Play, RotateCcw } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const SPEEDS = [1, 2, 4];

export function SiteHeader({
  playing,
  onToggle,
  onRestart,
  speed,
  onSpeed,
  done,
  total,
}: {
  playing: boolean;
  onToggle: () => void;
  onRestart: () => void;
  speed: number;
  onSpeed: (s: number) => void;
  done: number;
  total: number;
}) {
  const pct = total ? (done / total) * 100 : 0;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1560px] items-center gap-3 px-5">
        {/* Two files rather than a CSS filter: inverting would flip the brand blue too. */}
        <Image
          src="/ponder-lockup.png"
          alt="Ponder"
          width={510}
          height={128}
          priority
          className="h-6 w-auto dark:hidden"
        />
        <Image
          src="/ponder-lockup-dark.png"
          alt="Ponder"
          width={510}
          height={128}
          priority
          className="hidden h-6 w-auto dark:block"
        />
        <span className="hidden h-5 w-px bg-border sm:block" aria-hidden />
        <p className="hidden text-sm text-muted-foreground sm:block">Mission Control</p>

        <div className="mx-2 hidden h-8 items-center gap-2.5 rounded-lg border border-border bg-muted/40 px-3 md:flex">
          <span className="relative flex size-1.5">
            <span
              className={cn(
                "absolute inline-flex size-full rounded-full bg-live",
                playing && "breathe"
              )}
            />
          </span>
          <span className="text-xs text-muted-foreground">Replay</span>
          <span className="font-mono text-xs">
            {done}
            <span className="text-muted-foreground">/{total}</span>
          </span>
          <span className="h-1 w-20 overflow-hidden rounded-full bg-border">
            <span
              className="block h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${pct}%` }}
            />
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={onToggle}
                  aria-label={playing ? "Pause replay" : "Play replay"}
                >
                  {playing ? <Pause /> : <Play />}
                </Button>
              }
            />
            <TooltipContent>{playing ? "Pause" : "Play"}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={onRestart}
                  aria-label="Restart replay"
                >
                  <RotateCcw />
                </Button>
              }
            />
            <TooltipContent>Restart</TooltipContent>
          </Tooltip>

          <div
            role="group"
            aria-label="Replay speed"
            className="flex items-center gap-0.5 rounded-lg border border-border bg-muted/50 p-0.5"
          >
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSpeed(s)}
                aria-pressed={speed === s}
                className={cn(
                  "rounded-md px-2 py-1 font-mono text-[11px] transition-colors",
                  speed === s
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {s}×
              </button>
            ))}
          </div>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
