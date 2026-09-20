import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "./api";
import { AgentActivity, jobIsLive } from "./AgentActivity";
import { useAuth } from "./auth";
import { ExpenseDrawer } from "./ExpenseDrawer";
import { emptyJobProgress, formatCategory, formatMoney } from "./format";
import type { ExpenseDetail, JobDetail } from "./types";
import { Button, StatusPill } from "./ui";

const ACCEPT = "image/jpeg,image/png,application/pdf";
const JOBS_KEY = "expense-v2-process-jobs";

function jobsKey(orgId: string) {
  return `${JOBS_KEY}:${orgId}`;
}

function readStoredJobs(orgId: string): JobDetail[] {
  try {
    const raw = sessionStorage.getItem(jobsKey(orgId));
    const parsed = raw ? (JSON.parse(raw) as JobDetail[]) : [];
    return parsed.map(normalizeJob);
  } catch {
    return [];
  }
}

function normalizeJob(job: JobDetail): JobDetail {
  return {
    ...job,
    progress: job.progress ?? emptyJobProgress(),
  };
}

function writeStoredJobs(orgId: string, jobs: JobDetail[]) {
  sessionStorage.setItem(jobsKey(orgId), JSON.stringify(jobs));
}

export function ProcessPage() {
  const { token, currentOrg } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [expenses, setExpenses] = useState<ExpenseDetail[]>([]);
  const [watchingId, setWatchingId] = useState<string | null>(null);
  const viewId = searchParams.get("view");

  useEffect(() => {
    if (!currentOrg) {
      return;
    }
    setJobs(readStoredJobs(currentOrg.id));
    setWatchingId(null);
  }, [currentOrg]);

  useEffect(() => {
    if (!token || !currentOrg) {
      return;
    }
    api
      .listExpenses(token, currentOrg.id)
      .then((payload) => setExpenses(payload.items))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load files");
      });
  }, [token, currentOrg]);

  const liveCount = jobs.filter((job) => jobIsLive(job.status)).length;
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;

  useEffect(() => {
    if (!token || !currentOrg || liveCount === 0) {
      return;
    }
    const tick = async () => {
      const current = jobsRef.current;
      const updates = await Promise.all(
        current.map(async (job) => {
          if (!jobIsLive(job.status)) {
            return job;
          }
          try {
            return normalizeJob(await api.getJob(token, currentOrg.id, job.job_id));
          } catch {
            return job;
          }
        }),
      );
      setJobs(updates);
      writeStoredJobs(currentOrg.id, updates);
      if (updates.some((job) => !jobIsLive(job.status))) {
        const payload = await api.listExpenses(token, currentOrg.id);
        setExpenses(payload.items);
      }
    };
    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, 800);
    return () => window.clearInterval(timer);
  }, [liveCount, token, currentOrg]);

  const rows = useMemo(() => mergeRows(jobs, expenses), [jobs, expenses]);
  const selectedExpense = expenses.find((item) => item.expense_id === viewId);
  const watchedJob =
    jobs.find((job) => job.job_id === watchingId) ??
    jobs.find((job) => jobIsLive(job.status)) ??
    jobs[0] ??
    null;
  const watchedJobId = watchedJob?.job_id ?? null;

  useEffect(() => {
    if (!token || !currentOrg || !watchedJobId) {
      return;
    }
    let cancelled = false;
    api
      .getJob(token, currentOrg.id, watchedJobId)
      .then((job) => {
        if (cancelled) {
          return;
        }
        const updated = normalizeJob(job);
        setJobs((current) => {
          const next = current.map((item) =>
            item.job_id === updated.job_id ? updated : item,
          );
          writeStoredJobs(currentOrg.id, next);
          return next;
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [watchedJobId, token, currentOrg]);

  function openView(id: string) {
    const next = new URLSearchParams(searchParams);
    next.set("view", id);
    setSearchParams(next);
  }

  function closeView() {
    const next = new URLSearchParams(searchParams);
    next.delete("view");
    setSearchParams(next, { replace: true });
  }

  function addFiles(next: FileList | File[]) {
    setFiles((current) => [...current, ...Array.from(next)].slice(0, 10));
  }

  function removeFile(name: string, size: number) {
    setFiles((current) => current.filter((file) => file.name !== name || file.size !== size));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token || !currentOrg || files.length === 0) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      const result = await api.uploadReceipts(token, currentOrg.id, files);
      const details = await Promise.all(
        result.jobs.map((job) => api.getJob(token, currentOrg.id, job.job_id)),
      );
      const normalized = details.map(normalizeJob);
      const next = [...normalized, ...jobs].filter(
        (job, index, all) => all.findIndex((item) => item.job_id === job.job_id) === index,
      );
      setJobs(next);
      writeStoredJobs(currentOrg.id, next);
      setWatchingId(normalized[0]?.job_id ?? null);
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">Work</p>
      <h1 className="font-display mt-2 text-4xl">Process</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Upload one or more receipts here. Watch the agent read the file, decide each
        step, and fill merchant, date, amount, and category as it works.
      </p>

      <form
        className="mt-8 rounded-3xl border border-line bg-card p-4 sm:p-5"
        onSubmit={onSubmit}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
          <label
            className={`flex min-h-24 flex-1 cursor-pointer items-center justify-between gap-4 rounded-2xl border border-dashed px-5 py-4 ${
              dragging ? "border-accent bg-accent/5" : "border-line bg-paper/60"
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event: DragEvent<HTMLLabelElement>) => {
              event.preventDefault();
              setDragging(false);
              if (event.dataTransfer.files.length) {
                addFiles(event.dataTransfer.files);
              }
            }}
          >
            <input
              className="sr-only"
              type="file"
              accept={ACCEPT}
              multiple
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                if (event.target.files) {
                  addFiles(event.target.files);
                }
              }}
            />
            <div>
              <p className="text-sm font-semibold">Upload receipts</p>
              <p className="mt-1 text-xs text-muted">
                Drop or click to add JPEG, PNG, or PDF files. Up to 10 at once.
              </p>
            </div>
            <span className="rounded-full bg-void px-3 py-1 text-xs font-semibold text-paper">
              {files.length} selected
            </span>
          </label>
          <Button className="h-12 shrink-0 lg:w-40" type="submit" disabled={busy || files.length === 0}>
            {busy ? "Uploading…" : "Start processing"}
          </Button>
        </div>
        {files.length > 0 ? (
          <ul className="mt-4 flex flex-wrap gap-2">
            {files.map((file) => (
              <li
                key={`${file.name}-${file.size}`}
                className="flex items-center gap-2 rounded-full border border-line bg-paper px-3 py-1.5 text-xs"
              >
                <span className="max-w-48 truncate">{file.name}</span>
                <button
                  className="text-muted hover:text-ink"
                  type="button"
                  onClick={() => removeFile(file.name, file.size)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {error ? <p className="mt-3 text-sm text-rose-800">{error}</p> : null}
      </form>

      {watchedJob ? (
        <section className="mt-8">
          {jobs.length > 1 ? (
            <div className="mb-3 flex flex-wrap gap-2">
              {jobs.slice(0, 8).map((job) => (
                <button
                  key={job.job_id}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
                    job.job_id === watchedJob.job_id
                      ? "border-void bg-void text-paper"
                      : "border-line bg-card text-ink hover:bg-paper"
                  }`}
                  type="button"
                  onClick={() => setWatchingId(job.job_id)}
                >
                  {job.filename}
                  {jobIsLive(job.status) ? " · live" : ""}
                </button>
              ))}
            </div>
          ) : null}
          <AgentActivity
            filename={watchedJob.filename}
            status={watchedJob.status}
            progress={watchedJob.progress}
            errorMessage={watchedJob.error_message}
            footer={
              watchedJob.expense_id ? (
                <button
                  className="text-sm font-semibold underline decoration-line underline-offset-4"
                  type="button"
                  onClick={() => openView(watchedJob.expense_id!)}
                >
                  {watchedJob.status === "waiting_for_review" ? "Review this receipt" : "Open receipt details"}
                </button>
              ) : (
                <p className="text-xs text-muted">
                  Steps appear here as the agent thinks, calls tools, and retries.
                </p>
              )
            }
          />
        </section>
      ) : null}

      <section className="mt-8">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold">All files</h2>
            <p className="text-xs text-muted">{rows.length} rows · agent steps refresh while a file is running</p>
          </div>
        </div>
        <div className="overflow-x-auto rounded-3xl border border-line bg-card">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="text-[11px] font-semibold tracking-[0.12em] text-muted uppercase">
                <th className="px-5 py-4">File</th>
                <th className="px-5 py-4">Merchant</th>
                <th className="px-5 py-4">Date</th>
                <th className="px-5 py-4">Amount</th>
                <th className="px-5 py-4">Category</th>
                <th className="px-5 py-4">Status</th>
                <th className="px-5 py-4" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="px-5 py-16 text-center text-muted" colSpan={7}>
                    No files yet. Use the upload area above, then this table fills in as the agent finishes.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr
                    key={row.id}
                    className={`border-t border-line ${
                      row.expenseId === viewId ? "bg-paper/80" : "hover:bg-paper/50"
                    }`}
                  >
                    <td className="px-5 py-4 text-muted">{row.filename}</td>
                    <td className="px-5 py-4 font-medium">{row.merchant}</td>
                    <td className="px-5 py-4 tabular-nums">{row.date}</td>
                    <td className="px-5 py-4 tabular-nums">{row.amount}</td>
                    <td className="px-5 py-4 capitalize">{row.category}</td>
                    <td className="px-5 py-4">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="px-5 py-4 text-right">
                      {row.expenseId ? (
                        <button
                          className="rounded-full border border-line px-3 py-1 text-xs font-semibold hover:bg-void hover:text-paper"
                          type="button"
                          onClick={() => openView(row.expenseId!)}
                        >
                          {row.status === "needs_review" ? "Review" : "View"}
                        </button>
                      ) : row.jobId ? (
                        <button
                          className="rounded-full border border-line px-3 py-1 text-xs font-semibold hover:bg-void hover:text-paper"
                          type="button"
                          onClick={() => setWatchingId(row.jobId)}
                        >
                          Watch
                        </button>
                      ) : (
                        <span className="text-xs text-muted">Processing</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
      <ExpenseDrawer
        expenseId={viewId}
        initial={selectedExpense}
        onClose={closeView}
        onReviewed={(expense) => {
          setExpenses((current) =>
            current.map((item) =>
              item.expense_id === expense.expense_id ? expense : item,
            ),
          );
        }}
      />
    </main>
  );
}

type Row = {
  id: string;
  filename: string;
  merchant: string;
  date: string;
  amount: string;
  category: string;
  status: string;
  expenseId: string | null;
  jobId: string | null;
  createdAt: string;
};

function mergeRows(jobs: JobDetail[], expenses: ExpenseDetail[]): Row[] {
  const expenseIds = new Set(expenses.map((item) => item.expense_id));
  const fromExpenses: Row[] = expenses.map((expense) => ({
    id: expense.expense_id,
    filename: expense.filename ?? "—",
    merchant: expense.merchant ?? "—",
    date: expense.transaction_date ?? "—",
    amount: formatMoney(expense.total_minor_units, expense.currency),
    category: formatCategory(expense.category),
    status: expense.status,
    expenseId: expense.expense_id,
    jobId: expense.job_id,
    createdAt: expense.created_at,
  }));
  const fromJobs: Row[] = jobs
    .filter((job) => !job.expense_id || !expenseIds.has(job.expense_id))
    .map((job) => ({
      id: job.job_id,
      filename: job.filename,
      merchant: job.progress.merchant ?? "—",
      date: "—",
      amount: job.progress.total
        ? `${job.progress.currency ? `${job.progress.currency} ` : ""}${job.progress.total}`
        : "—",
      category: formatCategory(job.progress.category),
      status: job.status,
      expenseId: job.expense_id,
      jobId: job.job_id,
      createdAt: job.created_at,
    }));
  return [...fromJobs, ...fromExpenses].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}
