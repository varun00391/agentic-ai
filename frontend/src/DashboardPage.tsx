import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import { BarList, ColumnChart, DonutChart } from "./charts";
import { formatCategory, formatMoney } from "./format";
import type { ExpenseDetail } from "./types";
import { StatusPill } from "./ui";

const STATUS_COLORS = {
  accepted: "#12110f",
  needs_review: "#b45309",
  duplicate: "#0369a1",
  failed: "#be123c",
};

export function DashboardPage() {
  const { token, currentOrg } = useAuth();
  const [items, setItems] = useState<ExpenseDetail[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token || !currentOrg) {
      return;
    }
    api
      .listExpenses(token, currentOrg.id)
      .then((payload) => setItems(payload.items))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load dashboard");
      });
  }, [token, currentOrg]);

  const metrics = useMemo(() => summarize(items), [items]);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">Overview</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl">Dashboard</h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted">
            Totals for files already processed. Upload new receipts from Process.
          </p>
        </div>
        <Link
          to="/process"
          className="inline-flex h-10 items-center rounded-xl bg-void px-4 text-sm font-semibold text-paper"
        >
          Process files
        </Link>
      </div>

      {error ? <p className="mt-4 text-sm text-rose-800">{error}</p> : null}

      <section className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Files processed" value={String(metrics.files)} hint="Receipts posted to the ledger" />
        <Kpi label="Total spend" value={metrics.spend} hint="Sum of extracted totals" />
        <Kpi label="Needs review" value={String(metrics.review)} hint="Stopped for a human check" />
        <Kpi label="Success rate" value={metrics.successRate} hint="Accepted out of all files" />
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="File outcomes" subtitle="How each receipt finished">
          <DonutChart items={metrics.outcomes} />
        </Card>
        <Card title="Spend by category" subtitle="From extracted amounts">
          <BarList items={metrics.categories} empty="No spend categories yet." />
        </Card>
        <Card title="Files this week" subtitle="How many receipts landed each day">
          <ColumnChart items={metrics.daily} />
        </Card>
        <Card title="File types" subtitle="Based on uploaded filenames">
          <BarList items={metrics.fileTypes} empty="No file types yet." />
        </Card>
      </section>

      <section className="mt-6 overflow-hidden rounded-3xl border border-line bg-card">
        <div className="flex items-center justify-between px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold">Recent files</h2>
            <p className="text-xs text-muted">Latest receipts the agent posted</p>
          </div>
          <Link className="text-sm font-medium underline decoration-line underline-offset-4" to="/process">
            Open Process
          </Link>
        </div>
        {metrics.recent.length === 0 ? (
          <p className="border-t border-line px-5 py-12 text-center text-sm text-muted">
            Nothing here yet. Go to Process, upload receipts, and they will show up on this dashboard.
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-t border-line text-[11px] font-semibold tracking-[0.12em] text-muted uppercase">
                <th className="px-5 py-3">File</th>
                <th className="px-5 py-3">Merchant</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {metrics.recent.map((expense) => (
                <tr key={expense.expense_id} className="border-t border-line">
                  <td className="px-5 py-3 text-muted">{expense.filename ?? "—"}</td>
                  <td className="px-5 py-3 font-medium">{expense.merchant ?? "Untitled"}</td>
                  <td className="px-5 py-3 tabular-nums">
                    {formatMoney(expense.total_minor_units, expense.currency)}
                  </td>
                  <td className="px-5 py-3">
                    <StatusPill status={expense.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-3xl border border-line bg-card px-5 py-5">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-muted uppercase">{label}</p>
      <p className="font-display mt-3 text-3xl tracking-tight">{value}</p>
      <p className="mt-2 text-xs text-muted">{hint}</p>
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-line bg-card p-5">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-muted">{subtitle}</p>
      <div className="mt-5">{children}</div>
    </div>
  );
}

function summarize(items: ExpenseDetail[]) {
  const files = items.length;
  const review = items.filter((item) => item.status === "needs_review").length;
  const accepted = items.filter((item) => item.status === "accepted").length;
  const spendMinor = items.reduce((sum, item) => sum + (item.total_minor_units ?? 0), 0);
  const currency = items.find((item) => item.currency)?.currency ?? "USD";
  const outcomes = (["accepted", "needs_review", "duplicate", "failed"] as const).map((status) => ({
    label: status.replaceAll("_", " "),
    value: items.filter((item) => item.status === status).length,
    color: STATUS_COLORS[status],
  }));

  const categoryMap = new Map<string, number>();
  for (const item of items) {
    const key = formatCategory(item.category);
    const amount = (item.total_minor_units ?? 0) / 100;
    categoryMap.set(key, (categoryMap.get(key) ?? 0) + amount);
  }
  const categories = [...categoryMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([label, value]) => ({
      label,
      value: Number(value.toFixed(2)),
      color: "#12110f",
    }));

  const typeMap = new Map<string, number>();
  for (const item of items) {
    const ext = (item.filename?.split(".").pop() ?? "unknown").toUpperCase();
    typeMap.set(ext, (typeMap.get(ext) ?? 0) + 1);
  }
  const fileTypes = [...typeMap.entries()].map(([label, value]) => ({
    label,
    value,
    color: "#b45309",
  }));

  const days = lastDays(7);
  const byDay = new Map(days.map((day) => [day.key, 0]));
  for (const item of items) {
    const key = item.created_at.slice(0, 10);
    if (byDay.has(key)) {
      byDay.set(key, (byDay.get(key) ?? 0) + 1);
    }
  }
  const daily = days.map((day) => ({ label: day.label, value: byDay.get(day.key) ?? 0 }));
  const recent = [...items]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5);

  return {
    files,
    review,
    spend: formatMoney(spendMinor || null, files ? currency : null),
    successRate: files ? `${Math.round((accepted / files) * 100)}%` : "—",
    outcomes,
    categories,
    fileTypes,
    daily,
    recent,
  };
}

function lastDays(count: number) {
  const days = [];
  for (let i = count - 1; i >= 0; i -= 1) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    days.push({
      key: date.toISOString().slice(0, 10),
      label: date.toLocaleDateString(undefined, { weekday: "short" }),
    });
  }
  return days;
}
