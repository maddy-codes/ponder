"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Check, Copy, Download, FileJson, Loader2, Printer, ReceiptText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { download, isoOf, stamp } from "@/lib/export";
import {
  buildReceipt,
  gradeOutcome,
  isProvisional,
  type Receipt,
  receiptJson,
  receiptMarkdown,
  ruleVerdict,
  sandboxOutcome,
} from "@/lib/receipt";
import { bareId, type TaskEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-3 border-b border-border/60 py-1.5 last:border-b-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("text-xs break-words", mono && "font-mono")}>{value}</dd>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="mb-1 text-[11px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">
        {title}
      </h3>
      <dl>{children}</dl>
    </section>
  );
}

/**
 * An audit document for one exchange. Every line is a field of the TaskEvent it
 * fingerprints -- the receipt records what the agent decided and why, it does not
 * recompute anything.
 */
export function ReceiptDialog({
  event,
  trigger = "button",
}: {
  event: TaskEvent;
  trigger?: "button" | "icon";
}) {
  const [open, setOpen] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setReceipt(null);
    void buildReceipt(event).then((r) => live && setReceipt(r));
    return () => {
      live = false;
    };
  }, [open, event]);

  const base = `ponder-receipt-${bareId(event)}-${stamp()}`;

  async function copy() {
    if (!receipt) return;
    try {
      await navigator.clipboard.writeText(receiptMarkdown(receipt));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the download buttons still work */
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger === "icon" ? (
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={`Receipt for ${bareId(event)}`}
          title="Decision receipt"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
        >
          <ReceiptText />
        </Button>
      ) : (
        <Button variant="outline" size="xs" onClick={() => setOpen(true)}>
          <ReceiptText />
          Receipt
        </Button>
      )}

      <DialogContent
        className="flex max-h-[88vh] w-full flex-col gap-0 p-0 sm:max-w-2xl"
        showCloseButton={false}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3 print:hidden">
          <DialogTitle className="text-sm font-semibold">Decision receipt</DialogTitle>
          <DialogDescription className="sr-only">
            An audit record of how this task&rsquo;s compute budget was decided.
          </DialogDescription>
          <div className="ml-auto flex items-center gap-1.5 print:hidden">
            <Button variant="outline" size="xs" onClick={copy} disabled={!receipt}>
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button
              variant="outline"
              size="xs"
              disabled={!receipt}
              onClick={() =>
                receipt && download(`${base}.md`, "text/markdown", receiptMarkdown(receipt))
              }
            >
              <Download />
              .md
            </Button>
            <Button
              variant="outline"
              size="xs"
              disabled={!receipt}
              onClick={() =>
                receipt && download(`${base}.json`, "application/json", receiptJson(receipt))
              }
            >
              <FileJson />
              .json
            </Button>
            <Button variant="outline" size="xs" onClick={() => window.print()} disabled={!receipt}>
              <Printer />
              Print
            </Button>
            <DialogClose render={<Button variant="ghost" size="xs">Close</Button>} />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {!receipt ? (
            <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Sealing the record…
            </div>
          ) : (
            <article data-receipt className="bg-card px-5 py-5 text-foreground">
              <header className="flex items-start gap-3 border-b border-border pb-3">
                {/* data-logo lets the print stylesheet force the ink version, which a
                    dark:/print: class pair cannot do reliably. */}
                <Image
                  data-logo="light"
                  src="/ponder-mark.png"
                  alt=""
                  width={185}
                  height={192}
                  className="h-8 w-auto dark:hidden"
                />
                <Image
                  data-logo="dark"
                  src="/ponder-mark-dark.png"
                  alt=""
                  width={185}
                  height={192}
                  className="hidden h-8 w-auto dark:block"
                />
                <div>
                  <p className="text-sm font-semibold">Ponder — Decision Receipt</p>
                  <p className="text-xs text-muted-foreground">
                    How hard this task was thought about, and on whose authority
                  </p>
                </div>
                <div className="ml-auto min-w-0 text-right">
                  <p className="font-mono text-xs break-all">{receipt.number}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    issued {receipt.issuedAt}
                  </p>
                </div>
              </header>

              {isProvisional(event) && (
                <p className="mt-3 rounded-lg border border-stakes/40 bg-stakes/8 px-3 py-2 text-xs text-stakes">
                  <span className="font-semibold">Provisional</span> — this task had not finished
                  when the receipt was issued (status: {event.status}). Re-issue once it lands for
                  a final record.
                </p>
              )}

              <Block title="Request">
                <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs leading-relaxed">
                  {event.prompt_preview}
                </p>
              </Block>

              <Block title="Triage">
                <Row label="Difficulty" value={event.difficulty.toFixed(2)} mono />
                <Row label="Stakes" value={event.stakes.toFixed(2)} mono />
              </Block>

              <Block title="Policy">
                <Row
                  label="Matched rule"
                  value={event.matched_rule ?? "none"}
                  mono={Boolean(event.matched_rule)}
                />
                <Row label="Verdict" value={ruleVerdict(event)} />
                <Row label="Reason" value={event.rule_reason ?? "—"} />
                <Row label="Gateway rule" value={event.rule_id} mono />
              </Block>

              <Block title="Compute committed">
                <Row label="Budget" value={event.budget} />
                <Row label="Samples (best-of)" value={event.samples.length} mono />
                <Row
                  label="Total tokens"
                  value={event.total_tokens.toLocaleString("en-GB")}
                  mono
                />
                <Row label="Total GPU" value={`${event.total_gpu_seconds.toFixed(2)} s`} mono />
                <Row label="Latency" value={`${event.latency_ms} ms`} mono />
              </Block>

              {event.samples.length > 0 && (
                <div className="mt-2 overflow-hidden rounded-lg border border-border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 text-muted-foreground">
                      <tr>
                        <th className="px-2.5 py-1.5 text-left font-medium">Sample</th>
                        <th className="px-2.5 py-1.5 text-left font-medium">Status</th>
                        <th className="px-2.5 py-1.5 text-right font-medium">Tokens</th>
                        <th className="px-2.5 py-1.5 text-right font-medium">GPU (s)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {event.samples.map((s, i) => (
                        <tr key={i} className="border-t border-border/60">
                          <td className="px-2.5 py-1 font-mono">{i + 1}</td>
                          <td
                            className={cn(
                              "px-2.5 py-1",
                              s.status === "failed" && "text-miss"
                            )}
                          >
                            {s.status}
                          </td>
                          <td className="px-2.5 py-1 text-right font-mono">{s.tokens}</td>
                          <td className="px-2.5 py-1 text-right font-mono">
                            {s.gpu_seconds.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <Block title="Verification">
                <Row label="Sandbox" value={sandboxOutcome(event)} />
              </Block>

              <Block title="Result">
                <Row label="Answer" value={event.answer ?? "—"} mono />
                <Row label="Grade" value={gradeOutcome(event)} />
              </Block>

              <Block title="Provenance">
                <Row label="Event id" value={event.id} mono />
                <Row label="Strategy" value={event.strategy} />
                <Row label="Status" value={event.status} />
                <Row label="Emitted at" value={isoOf(event)} mono />
                <Row
                  label="Logfire trace"
                  value={
                    event.logfire_trace_url ? (
                      <a
                        href={event.logfire_trace_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-rule underline underline-offset-2"
                      >
                        {event.logfire_trace_url}
                      </a>
                    ) : (
                      "not captured for this run"
                    )
                  }
                />
                <Row label="Recording" value="events.jsonl" mono />
                <Row
                  label="Record fingerprint"
                  value={`${receipt.fingerprint}  (${receipt.fingerprintAlgorithm})`}
                  mono
                />
              </Block>

              <footer className="mt-5 border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
                Every value above is a field of the <code className="font-mono">TaskEvent</code>{" "}
                record this receipt fingerprints. Nothing is recomputed or inferred. Re-issuing the
                receipt for the same record yields the same number and fingerprint; a different
                fingerprint means the record changed.
              </footer>
            </article>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
