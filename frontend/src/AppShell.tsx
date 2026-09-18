import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./auth";
import { Button, Mark } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", end: true, icon: DashboardIcon },
  { to: "/process", label: "Process", end: false, icon: ProcessIcon },
  { to: "/settings", label: "Policy", end: false, icon: PolicyIcon },
];

export function AppShell() {
  const { displayName, email, currentOrg, organizations, selectOrg, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const initials = (displayName ?? email ?? "L")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col bg-void text-paper md:flex">
        <div className="px-5 py-5">
          <Mark inverse className="text-paper" />
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {NAV.map((item) => (
            <NavItem key={item.to} tone="dark" {...item} />
          ))}
        </nav>
        <AccountBlock
          tone="dark"
          initials={initials}
          email={email}
          currentOrgName={currentOrg?.name}
          currentOrgId={currentOrg?.id}
          organizations={organizations}
          onSelectOrg={selectOrg}
          onLogout={logout}
        />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-paper/90 px-4 py-3 md:hidden">
          <Mark />
          <button
            className="ml-auto rounded-lg px-2 py-1 text-sm text-muted"
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? "Close" : "Menu"}
          </button>
        </header>
        {menuOpen ? (
          <div className="border-b border-line bg-card px-3 py-3 md:hidden">
            <nav className="flex flex-col gap-1">
              {NAV.map((item) => (
                <NavItem key={item.to} tone="light" {...item} onClick={() => setMenuOpen(false)} />
              ))}
            </nav>
            <div className="mt-3 border-t border-line pt-3">
              <AccountBlock
                tone="light"
                compact
                initials={initials}
                email={email}
                currentOrgName={currentOrg?.name}
                currentOrgId={currentOrg?.id}
                organizations={organizations}
                onSelectOrg={selectOrg}
                onLogout={logout}
              />
            </div>
          </div>
        ) : null}
        <Outlet />
      </div>
    </div>
  );
}

function NavItem({
  to,
  label,
  end,
  icon: Icon,
  onClick,
  tone,
}: {
  to: string;
  label: string;
  end: boolean;
  icon: typeof DashboardIcon;
  onClick?: () => void;
  tone: "dark" | "light";
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${
          tone === "dark"
            ? isActive
              ? "bg-paper/12 text-paper"
              : "text-paper/60 hover:bg-paper/6 hover:text-paper"
            : isActive
              ? "bg-void text-paper"
              : "text-muted hover:bg-paper hover:text-ink"
        }`
      }
    >
      <Icon />
      {label}
    </NavLink>
  );
}

function AccountBlock({
  initials,
  email,
  currentOrgName,
  currentOrgId,
  organizations,
  onSelectOrg,
  onLogout,
  compact = false,
  tone,
}: {
  initials: string;
  email: string | null;
  currentOrgName?: string;
  currentOrgId?: string;
  organizations: { id: string; name: string }[];
  onSelectOrg: (id: string) => void;
  onLogout: () => void;
  compact?: boolean;
  tone: "dark" | "light";
}) {
  const dark = tone === "dark";
  return (
    <div className={`px-3 ${compact ? "" : "border-t border-paper/10 py-4"}`}>
      <div className="flex items-center gap-2">
        <span
          className={`flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-semibold ${
            dark ? "bg-paper text-void" : "bg-void text-paper"
          }`}
        >
          {initials}
        </span>
        <div className="min-w-0">
          <p className={`truncate text-xs font-medium ${dark ? "text-paper" : "text-ink"}`}>
            {currentOrgName}
          </p>
          <p className={`truncate text-[11px] ${dark ? "text-paper/50" : "text-muted"}`}>{email}</p>
        </div>
      </div>
      {organizations.length > 1 ? (
        <select
          className={`mt-3 h-9 w-full rounded-lg border px-2 text-xs ${
            dark ? "border-paper/15 bg-paper/8 text-paper" : "border-line bg-card text-ink"
          }`}
          value={currentOrgId ?? ""}
          onChange={(event) => onSelectOrg(event.target.value)}
        >
          {organizations.map((org) => (
            <option key={org.id} value={org.id}>
              {org.name}
            </option>
          ))}
        </select>
      ) : null}
      <Button
        tone="ghost"
        className={`mt-2 h-8 w-full px-2 text-xs ${dark ? "text-paper/70 hover:text-paper" : ""}`}
        type="button"
        onClick={onLogout}
      >
        Sign out
      </Button>
    </div>
  );
}

function DashboardIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="9" y="1.5" width="5.5" height="3.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="9" y="7" width="5.5" height="7.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="1.5" y="9" width="5.5" height="5.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function ProcessIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 11.5V13a1.5 1.5 0 0 0 1.5 1.5h7A1.5 1.5 0 0 0 13 13v-1.5M8 2.5v8M5 7.5 8 10.5 11 7.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PolicyIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 2.5 3.5 4.5v4.2c0 2.7 1.9 4.4 4.5 5.3 2.6-.9 4.5-2.6 4.5-5.3V4.5L8 2.5Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path
        d="M6.2 8.1 7.4 9.3 9.8 6.7"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
