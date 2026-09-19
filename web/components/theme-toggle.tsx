"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // The server cannot know the stored preference, so nothing is marked selected
  // until the client has mounted -- otherwise the first paint claims the wrong one.
  useEffect(() => setMounted(true), []);

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-lg border border-border bg-muted/50 p-0.5"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = mounted && theme === value;
        return (
          <Tooltip key={value}>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  onClick={() => setTheme(value)}
                  aria-pressed={active}
                  aria-label={`${label} theme`}
                  className={cn(
                    "flex size-6 items-center justify-center rounded-md transition-colors",
                    active
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                </button>
              }
            />
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
