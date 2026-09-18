import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

export function Mark({ className = "", inverse = false }: { className?: string; inverse?: boolean }) {
  const plate = inverse ? "#f6f1e8" : "#12110f";
  const glyph = inverse ? "#12110f" : "#f6f1e8";
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
        <rect width="22" height="22" rx="6" fill={plate} />
        <path
          d="M6.2 14.8V7.2h2.1l2.7 4.6 2.7-4.6h2.1v7.6h-1.8V10l-2.4 4.1h-1.2L8 10v4.8H6.2Z"
          fill={glyph}
        />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight">Ledger</span>
    </span>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
        {label}
      </span>
      {children}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`h-11 w-full rounded-xl border border-line bg-card px-3.5 text-sm text-ink placeholder:text-muted/70 ${props.className ?? ""}`}
    />
  );
}

export function Button({
  children,
  tone = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "ghost" }) {
  const styles =
    tone === "primary"
      ? "bg-void text-paper hover:bg-ink disabled:opacity-50"
      : "text-muted hover:text-ink";
  return (
    <button
      {...props}
      className={`inline-flex h-11 items-center justify-center rounded-xl px-5 text-sm font-semibold transition-colors ${styles} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    accepted: "bg-emerald-950 text-emerald-50",
    succeeded: "bg-emerald-950 text-emerald-50",
    needs_review: "bg-amber-100 text-amber-950",
    running: "bg-amber-100 text-amber-950",
    duplicate: "bg-sky-100 text-sky-950",
    failed: "bg-rose-100 text-rose-950",
    dead_letter: "bg-rose-100 text-rose-950",
    queued: "bg-stone-200 text-stone-800",
  };
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] ${map[status] ?? "bg-stone-200 text-stone-800"}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function AuthFrame({
  kicker,
  title,
  subtitle,
  children,
  footer,
}: {
  kicker: string;
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_0.95fr]">
      <aside className="relative hidden overflow-hidden bg-void px-12 py-14 text-paper lg:flex lg:flex-col lg:justify-between">
        <Mark inverse className="text-paper" />
        <div className="relative z-10 max-w-md py-16">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">
            {kicker}
          </p>
          <h2 className="font-display mt-5 text-5xl leading-[1.05] font-medium">
            Receipts in.
            <br />
            A ledger out.
          </h2>
          <p className="mt-5 text-sm leading-6 text-paper/70">
            An agent reads each document, checks totals, flags duplicates, and
            stops when a human should review.
          </p>
          <ol className="mt-10 space-y-4 text-sm">
            {[
              "Archive the original file",
              "Extract and normalize fields",
              "Validate, categorize, decide",
            ].map((step, index) => (
              <li key={step} className="flex gap-3 text-paper/80">
                <span className="font-display w-6 text-accent">0{index + 1}</span>
                {step}
              </li>
            ))}
          </ol>
        </div>
        <div
          className="pointer-events-none absolute -right-24 -bottom-24 h-80 w-80 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(180,83,9,0.35), transparent 68%)" }}
        />
      </aside>
      <main className="flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-[400px]">
          <div className="lg:hidden">
            <Mark />
          </div>
          <h1 className="font-display mt-10 text-4xl leading-tight lg:mt-0">{title}</h1>
          <p className="mt-3 text-sm leading-6 text-muted">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <p className="mt-8 text-sm text-muted">{footer}</p>
        </div>
      </main>
    </div>
  );
}

export function TextLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-ink underline decoration-line underline-offset-4">
      {children}
    </Link>
  );
}
