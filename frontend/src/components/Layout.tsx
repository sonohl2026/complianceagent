import { NavLink, Outlet } from "react-router-dom";

import { useDarkMode } from "../hooks/useDarkMode";

const PRIMARY_NAV_ITEMS = [
  { to: "/", label: "Products", end: true },
  { to: "/settings", label: "Settings" },
];

function navLinkClass({ isActive }: { isActive: boolean }) {
  return `block rounded px-3 py-1.5 text-sm ${
    isActive
      ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900"
  }`;
}

export function Layout() {
  const [isDark, toggleDark] = useDarkMode();

  return (
    <div className="flex min-h-screen">
      <aside className="w-64 shrink-0 border-r border-slate-200 dark:border-slate-800 p-4 flex flex-col">
        <div className="flex items-start justify-between gap-2 mb-6">
          <h1 className="text-sm font-semibold tracking-tight">
            MedTech Reimbursement
            <br />
            Readiness Agent
          </h1>
          <button
            onClick={toggleDark}
            aria-label="Toggle dark mode"
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            className="shrink-0 rounded border border-slate-300 dark:border-slate-700 px-2 py-1 text-xs hover:bg-slate-100 dark:hover:bg-slate-900"
          >
            {isDark ? "☀️" : "🌙"}
          </button>
        </div>
        <nav className="space-y-1">
          {PRIMARY_NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
