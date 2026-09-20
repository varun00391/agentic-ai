import { useEffect, useRef, type ReactNode } from "react";
import {
  formatCategory,
  formatExtraction,
  formatObservation,
  formatPolicy,
  formatToolArguments,
  formatToolName,
} from "./format";
import type { JobProgress, TraceEvent } from "./types";
import { StatusPill } from "./ui";

type Props = {
  filename: string;
  status: string;
  progress: JobProgress;
  errorMessage?: string | null;
  compact?: boolean;
  footer?: ReactNode;
};

export function jobIsLive(status: string): boolean {
  return status === "queued" || status === "running";
}

function activityStatusLabel(
  status: string,
  live: boolean,
  working: boolean,
  progress: JobProgress,
): string {
  if (live) {
    if (working) {
      if (progress.current_tool) {
        return `Working · ${formatToolName(progress.current_tool)}`;
      }
      return progress.current_reason || "Starting…";
    }
    return status === "queued" ? "Waiting for a worker" : "Starting…";
  }
  if (status === "waiting_for_review" || status === "needs_review") {
    return "Paused for your review";
  }
  if (status === "succeeded" || status === "accepted") {
    return "Finished this receipt";
  }
  if (status === "duplicate") {
    return "Marked as a duplicate";
  }
  if (status === "failed" || status === "dead_letter") {
    return "Stopped with an error";
  }
  if (status === "rejected") {
    return "Rejected";
  }
  return status.replaceAll("_", " ");
}

export function AgentActivity({
  filename,
  status,
  progress,
  errorMessage,
  compact = false,
  footer,
}: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const live = jobIsLive(status);
  const displayStatus = progress.final_status || status;
  const working = Boolean(progress.current_reason);
  const steps = progress.trace;

  useEffect(() => {
    const node = scroller.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [steps.length, progress.current_tool, progress.current_reason, status]);

  return (
    <section
      className={`overflow-hidden border border-line bg-card ${
        compact ? "rounded-2xl" : "rounded-3xl"
      }`}
    >
      <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold tracking-[0.16em] text-accent uppercase">
            Agent
          </p>
          <h2 className="mt-1 truncate text-sm font-semibold">{filename}</h2>
          <p className="mt-1 text-xs text-muted">
            {activityStatusLabel(displayStatus, live, working, progress)}
            {progress.item_count > 1
              ? ` · Item ${Math.min(progress.item_index, progress.item_count - 1) + 1} of ${progress.item_count}`
              : ""}
          </p>
        </div>
        <StatusPill status={displayStatus} />
      </header>

      <div
        ref={scroller}
        className={`space-y-4 overflow-y-auto px-5 py-5 ${compact ? "max-h-[28rem]" : "max-h-[32rem]"}`}
      >
        {compact ? null : (
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-void px-4 py-3 text-sm text-paper">
              Uploaded {filename}
            </div>
          </div>
        )}

        {steps.map((event) => (
          <TraceStep key={`${event.step}-${event.tool}`} event={event} />
        ))}

        {live && working ? (
          <WorkingStep
            tool={progress.current_tool}
            reason={progress.current_reason}
            arguments_={progress.current_arguments}
          />
        ) : null}

        {!live && steps.length === 0 ? (
          <p className="text-sm text-muted">No agent steps were recorded for this file.</p>
        ) : null}

        {errorMessage ? (
          <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-950">{errorMessage}</p>
        ) : null}

        {!compact &&
        (progress.merchant || progress.total || progress.category || progress.policy_decision) ? (
          <dl className="grid grid-cols-2 gap-2 rounded-2xl bg-paper px-4 py-3 text-xs">
            <Fact label="Merchant" value={progress.merchant} />
            <Fact
              label="Amount"
              value={
                progress.total
                  ? `${progress.currency ? `${progress.currency} ` : ""}${progress.total}`
                  : null
              }
            />
            <Fact label="Category" value={progress.category ? formatCategory(progress.category) : null} />
            <Fact
              label="Confidence"
              value={formatExtraction(
                progress.extraction_confidence,
                progress.extraction_source,
              )}
            />
            <Fact
              label="Policy"
              value={progress.policy_decision ? formatPolicy(progress.policy_decision) : null}
            />
          </dl>
        ) : null}
      </div>
      {footer ? <div className="border-t border-line px-5 py-3">{footer}</div> : null}
    </section>
  );
}

function TraceStep({ event }: { event: TraceEvent }) {
  return (
    <article className="flex gap-3">
      <span
        className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
          event.success ? "bg-void" : "bg-rose-600"
        }`}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm font-medium">{formatToolName(event.tool)}</p>
          <p className="text-[11px] tracking-wide text-muted uppercase">
            {event.success ? "Done" : "Failed"}
          </p>
        </div>
        {event.reason ? (
          <p className="mt-1 text-sm leading-6 text-muted italic">{event.reason}</p>
        ) : null}
        <p className="mt-1 text-sm leading-6">{formatObservation(event)}</p>
      </div>
    </article>
  );
}

function WorkingStep({
  tool,
  reason,
  arguments_,
}: {
  tool: string | null;
  reason: string | null;
  arguments_: Record<string, unknown>;
}) {
  const extra = formatToolArguments(arguments_);
  return (
    <article className="flex gap-3">
      <span className="agent-live-dot mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-accent" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {tool ? formatToolName(tool) : "Thinking"}
        </p>
        <p className="mt-1 text-sm leading-6 text-muted italic">
          {reason ?? "Working on this receipt…"}
          {extra ? ` · ${extra}` : ""}
        </p>
        <p className="agent-typing mt-2 flex gap-1" aria-hidden="true">
          <span className="h-1.5 w-1.5 rounded-full bg-muted" />
          <span className="h-1.5 w-1.5 rounded-full bg-muted" />
          <span className="h-1.5 w-1.5 rounded-full bg-muted" />
        </p>
      </div>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  if (!value || value === "—") {
    return null;
  }
  return (
    <div>
      <dt className="text-[10px] font-semibold tracking-[0.12em] text-muted uppercase">{label}</dt>
      <dd className="mt-0.5 truncate text-sm">{value}</dd>
    </div>
  );
}
