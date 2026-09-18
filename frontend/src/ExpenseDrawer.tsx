import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import {
  formatCategory,
  formatDisplayDate,
  formatExtraction,
  formatMoney,
  formatPolicy,
} from "./format";
import { AgentActivity } from "./AgentActivity";
import type { ExpenseDetail } from "./types";
import { Button, Field, StatusPill, TextInput } from "./ui";

const CATEGORIES = [
  "food_and_dining",
  "groceries",
  "transport",
  "utilities",
  "shopping",
  "health",
  "entertainment",
  "travel",
  "education",
  "other",
] as const;

type Props = {
  expenseId: string | null;
  initial?: ExpenseDetail;
  onClose: () => void;
  onReviewed?: (expense: ExpenseDetail) => void;
};

export function ExpenseDrawer({ expenseId, initial, onClose, onReviewed }: Props) {
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

  const canReview =
    expense?.status === "needs_review" && currentOrg?.role !== "auditor";

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
          {expense ? (
            <ReceiptBody
              expense={expense}
              canReview={Boolean(canReview && token && currentOrg)}
              onUpdated={(next) => {
                setExpense(next);
                onReviewed?.(next);
              }}
            />
          ) : null}
        </div>
      </aside>
    </div>,
    document.body,
  );
}

function ReceiptBody({
  expense,
  canReview,
  onUpdated,
}: {
  expense: ExpenseDetail;
  canReview: boolean;
  onUpdated: (expense: ExpenseDetail) => void;
}) {
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

      {canReview ? (
        <ReviewForm expense={expense} onUpdated={onUpdated} />
      ) : (
        <dl className="mt-6 divide-y divide-line overflow-hidden rounded-2xl border border-line">
          <Fact label="Date" value={formatDisplayDate(expense.transaction_date)} />
          <Fact label="Category" value={formatCategory(expense.category)} />
          <Fact
            label="Extraction"
            value={formatExtraction(
              expense.extraction_confidence,
              expense.extraction_source,
            )}
          />
          <Fact label="Policy" value={formatPolicy(expense.policy_decision)} />
          <Fact label="Source file" value={expense.filename ?? "—"} />
        </dl>
      )}

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
        <div className="mt-8 pb-4">
          <AgentActivity
            compact
            filename={expense.filename ?? "Receipt"}
            status={expense.status}
            progress={{
              step_count: expense.step_count,
              current_tool: null,
              current_reason: null,
              current_arguments: {},
              merchant: expense.merchant,
              total:
                expense.total_minor_units === null
                  ? null
                  : (expense.total_minor_units / 100).toFixed(2),
              currency: expense.currency,
              category: expense.category,
              extraction_confidence: expense.extraction_confidence,
              extraction_source: expense.extraction_source,
              policy_decision: expense.policy_decision,
              final_status: expense.status,
              item_index: 0,
              item_count: 0,
              trace: expense.trace,
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

function ReviewForm({
  expense,
  onUpdated,
}: {
  expense: ExpenseDetail;
  onUpdated: (expense: ExpenseDetail) => void;
}) {
  const { token, currentOrg } = useAuth();
  const [merchant, setMerchant] = useState(expense.merchant ?? "");
  const [transactionDate, setTransactionDate] = useState(expense.transaction_date ?? "");
  const [total, setTotal] = useState(amountInput(expense.total_minor_units));
  const [category, setCategory] = useState(expense.category ?? "other");
  const [busy, setBusy] = useState<"approve" | "edit" | "reject" | "">("");
  const [error, setError] = useState("");

  useEffect(() => {
    setMerchant(expense.merchant ?? "");
    setTransactionDate(expense.transaction_date ?? "");
    setTotal(amountInput(expense.total_minor_units));
    setCategory(expense.category ?? "other");
    setError("");
  }, [expense.expense_id]);

  async function submit(decision: "approve" | "edit" | "reject") {
    if (!token || !currentOrg) {
      return;
    }
    setBusy(decision);
    setError("");
    try {
      const payload =
        decision === "reject"
          ? { decision }
          : decision === "approve"
            ? { decision }
            : {
                decision,
                merchant,
                transaction_date: transactionDate,
                total,
                category,
              };
      const next = await api.reviewExpense(
        token,
        currentOrg.id,
        expense.expense_id,
        payload,
      );
      onUpdated(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save this review");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="mt-6 rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-amber-900 uppercase">
        Waiting for review
      </p>
      <p className="mt-1 text-sm leading-6 text-amber-950/80">
        The agent paused here. Approve the guessed fields, edit them, or reject the
        receipt.
      </p>
      <div className="mt-4 space-y-3">
        <Field label="Merchant">
          <TextInput value={merchant} onChange={(event) => setMerchant(event.target.value)} />
        </Field>
        <Field label="Date">
          <TextInput
            value={transactionDate}
            placeholder="2026-09-01"
            onChange={(event) => setTransactionDate(event.target.value)}
          />
        </Field>
        <Field label="Amount">
          <TextInput
            value={total}
            inputMode="decimal"
            placeholder="123.45"
            onChange={(event) => setTotal(event.target.value)}
          />
        </Field>
        <Field label="Category">
          <select
            className="h-11 w-full rounded-xl border border-line bg-card px-3.5 text-sm text-ink"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {formatCategory(item)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {error ? <p className="mt-3 text-sm text-rose-800">{error}</p> : null}
      <div className="mt-4 flex flex-col gap-2">
        <Button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => submit("approve")}
        >
          {busy === "approve" ? "Approving…" : "Approve as-is"}
        </Button>
        <Button
          type="button"
          className="border border-line bg-card text-ink hover:bg-paper"
          disabled={Boolean(busy)}
          onClick={() => submit("edit")}
        >
          {busy === "edit" ? "Saving…" : "Save edits"}
        </Button>
        <Button
          type="button"
          tone="danger"
          disabled={Boolean(busy)}
          onClick={() => submit("reject")}
        >
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </Button>
      </div>
    </section>
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

function amountInput(totalMinorUnits: number | null): string {
  if (totalMinorUnits === null) {
    return "";
  }
  return (totalMinorUnits / 100).toFixed(2);
}
