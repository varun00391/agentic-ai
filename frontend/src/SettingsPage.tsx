import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import { formatCategory } from "./format";
import type { OrganizationPolicy } from "./types";
import { Button, Field, TextInput } from "./ui";

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

export function SettingsPage() {
  const { token, currentOrg } = useAuth();
  const [policy, setPolicy] = useState<OrganizationPolicy | null>(null);
  const [confidence, setConfidence] = useState("70");
  const [maxAmount, setMaxAmount] = useState("");
  const [alwaysReview, setAlwaysReview] = useState<string[]>([]);
  const [reviewAll, setReviewAll] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const canEdit = currentOrg?.role === "owner" || currentOrg?.role === "admin";

  useEffect(() => {
    if (!token || !currentOrg) {
      return;
    }
    api
      .getPolicy(token, currentOrg.id)
      .then((payload) => {
        setPolicy(payload);
        setConfidence(String(Math.round(payload.extraction_min_confidence * 100)));
        setMaxAmount(
          payload.max_auto_accept_minor_units === null
            ? ""
            : (payload.max_auto_accept_minor_units / 100).toFixed(2),
        );
        setAlwaysReview(payload.always_review_categories);
        setReviewAll(payload.review_all);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load policy");
      });
  }, [token, currentOrg]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token || !currentOrg || !canEdit) {
      return;
    }
    const parsedConfidence = Number(confidence);
    if (!Number.isFinite(parsedConfidence) || parsedConfidence < 0 || parsedConfidence > 100) {
      setError("Confidence must be between 0 and 100");
      return;
    }
    let maxMinor: number | null = null;
    if (maxAmount.trim()) {
      const parsedAmount = Number(maxAmount);
      if (!Number.isFinite(parsedAmount) || parsedAmount < 0) {
        setError("Auto-accept amount must be a positive number");
        return;
      }
      maxMinor = Math.round(parsedAmount * 100);
    }
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const payload = await api.updatePolicy(token, currentOrg.id, {
        extraction_min_confidence: parsedConfidence / 100,
        max_auto_accept_minor_units: maxMinor,
        always_review_categories: alwaysReview,
        review_all: reviewAll,
      });
      setPolicy(payload);
      setSaved("Policy saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save policy");
    } finally {
      setBusy(false);
    }
  }

  function toggleCategory(category: string) {
    setAlwaysReview((current) =>
      current.includes(category)
        ? current.filter((item) => item !== category)
        : [...current, category],
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
        Organization
      </p>
      <h1 className="font-display mt-2 text-4xl">Policy</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Control when the agent auto-accepts an expense, and see merchants learned from
        human corrections.
      </p>

      <form className="mt-8 space-y-6 rounded-3xl border border-line bg-card p-5" onSubmit={onSubmit}>
        <Field label="Minimum extraction confidence (%)">
          <TextInput
            value={confidence}
            inputMode="numeric"
            disabled={!canEdit}
            onChange={(event) => setConfidence(event.target.value)}
          />
        </Field>
        <Field label="Auto-accept up to amount (empty = no extra cap)">
          <TextInput
            value={maxAmount}
            inputMode="decimal"
            placeholder="5000.00"
            disabled={!canEdit}
            onChange={(event) => setMaxAmount(event.target.value)}
          />
        </Field>
        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={reviewAll}
            disabled={!canEdit}
            onChange={(event) => setReviewAll(event.target.checked)}
          />
          Review every expense
        </label>
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Always review these categories
          </p>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((category) => {
              const selected = alwaysReview.includes(category);
              return (
                <button
                  key={category}
                  type="button"
                  disabled={!canEdit}
                  onClick={() => toggleCategory(category)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
                    selected
                      ? "border-void bg-void text-paper"
                      : "border-line bg-paper text-ink"
                  }`}
                >
                  {formatCategory(category)}
                </button>
              );
            })}
          </div>
        </div>
        {error ? <p className="text-sm text-rose-800">{error}</p> : null}
        {saved ? <p className="text-sm text-emerald-800">{saved}</p> : null}
        {canEdit ? (
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save policy"}
          </Button>
        ) : (
          <p className="text-sm text-muted">Only owners and admins can change policy.</p>
        )}
      </form>

      <section className="mt-8 rounded-3xl border border-line bg-card p-5">
        <h2 className="text-sm font-semibold">Merchant memory</h2>
        <p className="mt-1 text-xs text-muted">
          Learned when someone edits or approves a receipt. Used the next time that shop appears.
        </p>
        {policy && policy.merchant_memories.length > 0 ? (
          <ul className="mt-4 divide-y divide-line">
            {policy.merchant_memories.map((item) => (
              <li key={`${item.merchant}-${item.category}`} className="flex justify-between gap-4 py-3 text-sm">
                <span className="font-medium">{item.merchant}</span>
                <span className="text-muted">{formatCategory(item.category)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-sm text-muted">No corrections stored yet.</p>
        )}
      </section>
    </main>
  );
}
