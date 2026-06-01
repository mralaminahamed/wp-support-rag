// App layout: sidebar + topbar + routed content. Author: Al Amin Ahamed.
import { Boxes, LayoutDashboard, LogOut, MessageSquare, Settings, Users } from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Logo } from "@/components/Logo";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { ConnectionBadge } from "./ConnectionBadge";
import { ThemeToggle } from "./ThemeToggle";

const NAV: Array<{
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  permission?: string;
}> = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/plugins", label: "Plugins", icon: Boxes },
  { to: "/playground", label: "Playground", icon: MessageSquare },
  { to: "/users", label: "Users", icon: Users, permission: "users:read" },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const { user, logout, hasPermission } = useAuth();

  return (
    <div className="grid min-h-screen grid-cols-[232px_1fr] max-md:grid-cols-1">
      <aside className="sticky top-0 flex h-screen flex-col gap-1 border-r border-sidebar-border bg-sidebar p-3.5 max-md:hidden">
        <div className="flex items-center gap-2.5 px-2 pb-4 pt-1 font-bold text-sidebar-foreground">
          <Logo size={24} />
          <span>Support RAG</span>
        </div>
        {NAV.filter((n) => !n.permission || hasPermission(n.permission)).map(
          ({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-sidebar-accent hover:text-foreground",
                  isActive && "bg-sidebar-accent text-sidebar-accent-foreground",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ),
        )}
        <div className="flex-1" />
        <div className="flex items-center gap-2 rounded-lg px-2 py-2">
          <Avatar name={user?.email ?? "?"} email={user?.email ?? ""} size={32} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-sidebar-foreground">
              {user?.email ?? ""}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {user?.roles.join(", ") ?? ""}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Sign out"
            onClick={() => void logout()}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-10 flex h-15 items-center gap-3 border-b border-border bg-card/80 px-6 backdrop-blur">
          <span className="font-semibold md:hidden">Support RAG</span>
          <div className="flex-1" />
          <ConnectionBadge />
          <ThemeToggle />
          <Avatar name={user?.email ?? "?"} email={user?.email ?? ""} size={30} />
        </header>
        <main className="mx-auto w-full max-w-[1100px] p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
