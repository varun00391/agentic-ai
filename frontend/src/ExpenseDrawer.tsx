import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import {
  formatCategory,
  formatDisplayDate,
  formatMoney,
  formatPolicy,
  formatToolName,
} from "./format";
import type { ExpenseDetail, TraceEvent } from "./types";
import { StatusPill } from "./ui";

type Props = {
  expenseId: string | null;
  initial?: ExpenseDetail;
  onClose: () => void;
};

export function ExpenseDrawer({ expenseId, initial, onClose }: Props) {
  const { token, currentOrg } = useAuth();
  const [expense, setExpense] = useState<ExpenseDetail | null>(initial ?? null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!expenseId) {
      setExpense(null);
      setError("");
      return;
    }
    setExpense(initial ?? null);
    if (!token || !currentOrg) {
      return;
    }
    api
      .getExpense(token, currentOrg.id, expenseId)
      .then((payload) => {
        setExpense(payload);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load this receipt");
      });
  }, [expenseId, token, currentOrg]);

  useEffect(() => {
    if (!expenseId) {
      return;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [expenseId, onClose]);

  if (!expenseId) {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        aria-label="Close receipt details"
        className="drawer-overlay absolute inset-0 bg-void/45"
        type="button"
        onClick={onClose}
      />
      <aside
        className="drawer-panel relative flex h-full w-full max-w-[440px] flex-col bg-card shadow-[-24px_0_60px_rgba(18,17,15,0.18)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="receipt-drawer-title"
      >
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <p className="text-[11px] font-semibold tracking-[0.16em] text-muted uppercase">
            Receipt details
          </p>
          <button
            className="rounded-full px-3 py-1 text-sm text-muted hover:bg-paper hover:text-ink"
            type="button"
            onClick={onClose}
          >
            Close
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {error ? <p className="text-sm text-rose-800">{error}</p> : null}
          {!error && !expense ? (
            <p className="text-sm text-muted">Opening receipt…</p>
          ) : null}
          {expense ? <ReceiptBody expense={expense} /> : null}
        </div>
      </aside>
    </div>,
    document.body,
  );
}

function ReceiptBody({ expense }: { expense: ExpenseDetail }) {
  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="receipt-drawer-title" className="font-display text-3xl leading-tight">
            {expense.merchant ?? "Untitled receipt"}
          </h2>
          <p className="mt-1 truncate text-sm text-muted">{expense.filename ?? "No file name"}</p>
        </div>
        <StatusPill status={expense.status} />
      </div>

      <div className="mt-6 rounded-3xl bg-void px-5 py-6 text-paper">
        <p className="text-[11px] font-semibold tracking-[0.16em] text-accent uppercase">Paid</p>
        <p className="font-display mt-2 text-4xl tracking-tight">
          {formatMoney(expense.total_minor_units, expense.currency)}
        </p>
        <p className="mt-2 text-sm text-paper/65">
          {formatDisplayDate(expense.transaction_date)}
          {expense.category ? ` · ${formatCategory(expense.category)}` : ""}
        </p>
      </div>

      <dl className="mt-6 divide-y divide-line overflow-hidden rounded-2xl border border-line">
        <Fact label="Date" value={formatDisplayDate(expense.transaction_date)} />
        <Fact label="Category" value={formatCategory(expense.category)} />
        <Fact label="Policy" value={formatPolicy(expense.policy_decision)} />
        <Fact label="Source file" value={expense.filename ?? "—"} />
      </dl>

      {expense.duplicate_of_expense_id ? (
        <p className="mt-4 rounded-2xl bg-sky-50 px-4 py-3 text-sm text-sky-950">
          This looks like a duplicate of an earlier receipt.
        </p>
      ) : null}

      {expense.messages.length > 0 ? (
        <section className="mt-8">
          <h3 className="text-[11px] font-semibold tracking-[0.14em] text-muted uppercase">
            Notes
          </h3>
          <ul className="mt-3 space-y-2 text-sm leading-6">
            {expense.messages.map((message) => (
              <li key={message} className="rounded-xl bg-paper px-4 py-3">
                {message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {expense.trace.length > 0 ? (
        <section className="mt-8 pb-4">
          <h3 className="text-[11px] font-semibold tracking-[0.14em] text-muted uppercase">
            How this was processed
          </h3>
          <ol className="mt-4 space-y-0">
            {expense.trace.map((event, index) => (
              <li key={`${event.step}-${event.tool}`} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span
                    className={`mt-1 h-2.5 w-2.5 rounded-full ${
                      event.success ? "bg-void" : "bg-rose-600"
                    }`}
                  />
                  {index < expense.trace.length - 1 ? (
                    <span className="w-px flex-1 bg-line" />
                  ) : null}
                </div>
                <div className="pb-5">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-sm font-medium">{formatToolName(event.tool)}</p>
                    <p className="text-[11px] tracking-wide text-muted uppercase">
                      {event.success ? "Done" : "Failed"}
                    </p>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-muted">
                    {formatObservation(event)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 bg-card px-4 py-3.5">
      <dt className="text-xs tracking-wide text-muted uppercase">{label}</dt>
      <dd className="max-w-[60%] text-right text-sm">{value}</dd>
    </div>
  );
}

function formatObservation(event: TraceEvent): string {
  if (event.tool === "save_result" && event.success) {
    return "Saved to your ledger";
  }
  if (event.tool === "build_final_result") {
    return event.observation.replaceAll("_", " ");
  }
  return event.observation;
}
