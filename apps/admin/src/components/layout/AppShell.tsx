// App layout: sidebar + topbar + routed content. Author: Al Amin Ahamed.
import { Boxes, LayoutDashboard, MessageSquare, Settings } from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ConnectionBadge } from "./ConnectionBadge";
import { ThemeToggle } from "./ThemeToggle";

const NAV: Array<{ to: string; label: string; icon: ComponentType<{ className?: string }> }> = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/plugins", label: "Plugins", icon: Boxes },
  { to: "/playground", label: "Playground", icon: MessageSquare },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  return (
    <div className="grid min-h-screen grid-cols-[232px_1fr] max-md:grid-cols-1">
      <aside className="sticky top-0 flex h-screen flex-col gap-1.5 border-r border-border bg-surface p-3.5 max-md:hidden">
        <div className="flex items-center gap-2.5 px-2 pb-4 pt-1 font-bold">
          <span className="h-5.5 w-5.5 rounded-md bg-accent" style={{ width: 22, height: 22 }} />
          <span>Support RAG</span>
        </div>
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 font-medium text-muted hover:bg-surface-2 hover:text-fg",
                isActive && "bg-accent-soft text-accent hover:bg-accent-soft hover:text-accent",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
        <div className="flex-1" />
        <p className="px-3 text-xs text-muted">Al Amin Ahamed</p>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-10 flex h-15 items-center gap-3 border-b border-border bg-surface px-6 py-3.5">
          <span className="font-semibold">Admin</span>
          <div className="flex-1" />
          <ConnectionBadge />
          <ThemeToggle />
        </header>
        <main className="mx-auto w-full max-w-[1100px] p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
