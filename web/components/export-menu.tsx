"use client";

import { ChevronDown, Download, FileJson, FileSpreadsheet, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { download, stamp, toCsv, toJson, toJsonl } from "@/lib/export";
import type { TaskEvent } from "@/lib/types";

/**
 * Export what is on screen, or the whole recording. Both come out of the client --
 * the events are already loaded, so no route is added and the dashboard stays a renderer.
 */
export function ExportMenu({
  view,
  all,
  viewLabel,
}: {
  /** the rows the filters and search currently leave standing */
  view: TaskEvent[];
  /** every landed event, whatever the filters say */
  all: TaskEvent[];
  viewLabel: string;
}) {
  const filtered = view.length !== all.length;
  const name = (ext: string, scope: string) => `ponder-log-${scope}-${stamp()}.${ext}`;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="outline" size="xs">
            <Download />
            Export
            <ChevronDown data-icon="inline-end" />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-64">
        {/* Base UI labels are group labels: outside a Group they throw and the menu dies. */}
        <DropdownMenuGroup>
          <DropdownMenuLabel>
            This view — {view.length} task{view.length === 1 ? "" : "s"}
            {filtered ? ` (${viewLabel})` : ""}
          </DropdownMenuLabel>
          <DropdownMenuItem onClick={() => download(name("csv", "view"), "text/csv", toCsv(view))}>
            <FileSpreadsheet />
            CSV — one row per task
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              download(name("json", "view"), "application/json", toJson(view, viewLabel))
            }
          >
            <FileJson />
            JSON — with export envelope
          </DropdownMenuItem>
        </DropdownMenuGroup>

        <DropdownMenuSeparator />

        <DropdownMenuGroup>
          <DropdownMenuLabel>
            Whole run — {all.length} task{all.length === 1 ? "" : "s"}
          </DropdownMenuLabel>
          <DropdownMenuItem onClick={() => download(name("csv", "run"), "text/csv", toCsv(all))}>
            <FileSpreadsheet />
            CSV — one row per task
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => download(name("jsonl", "run"), "application/x-ndjson", toJsonl(all))}
          >
            <FileText />
            JSONL — verbatim event records
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
