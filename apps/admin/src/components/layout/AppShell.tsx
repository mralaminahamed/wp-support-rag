// App layout: collapsible navy sidebar + routed content. Author: Al Amin Ahamed.
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Logo } from "@/components/Logo";
import { Avatar } from "@/components/ui/avatar";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { ConnectionBadge } from "./ConnectionBadge";
import { ThemeToggle } from "./ThemeToggle";

const NAV: Array<{
  to: string;
  label: string;
  icon: string;
  permission?: string;
  exact?: boolean;
}> = [
  { to: "/", label: "Dashboard", icon: "ti-layout-dashboard", exact: true },
  { to: "/plugins", label: "Plugins", icon: "ti-puzzle" },
  { to: "/playground", label: "Playground", icon: "ti-message-chatbot" },
  { to: "/users", label: "Users", icon: "ti-users", permission: "users:read" },
  { to: "/tickets", label: "Tickets", icon: "ti-ticket", permission: "plugins:read" },
  { to: "/adapters", label: "Adapters", icon: "ti-plug" },
];

function NavItem({
  to,
  label,
  icon,
  exact,
  collapsed,
}: {
  to: string;
  label: string;
  icon: string;
  exact?: boolean;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={exact}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          "flex items-center py-2 text-[13px] font-medium rounded-r-lg",
          "border-l-2 -ml-2 transition-colors cursor-pointer select-none",
          collapsed ? "justify-center px-3" : "gap-2.5 px-4",
          isActive
            ? "bg-nav-active-bg text-nav-text-active border-l-primary"
            : "text-nav-text border-l-transparent hover:bg-white/5 hover:text-nav-text-hover",
        )
      }
    >
      <i aria-hidden="true" className={`ti ${icon} text-base shrink-0`} />
      {!collapsed && <span className="flex-1 truncate">{label}</span>}
    </NavLink>
  );
}

export function AppShell() {
  const { user, logout, hasPermission } = useAuth();
  const navigate = useNavigate();

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebar-collapsed") === "true",
  );

  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem("sidebar-collapsed", String(next));
      return next;
    });
  }

  return (
    <div className="flex min-h-screen w-full">
      {/* Sidebar */}
      <aside
        className={cn(
          "bg-nav flex flex-col shrink-0 transition-[width] duration-200 ease-in-out overflow-x-hidden max-md:hidden",
          collapsed ? "w-14" : "w-54",
        )}
        style={{ backgroundColor: "var(--nav)" }}
      >
        {/* Logo */}
        <div
          className={cn(
            "py-4 border-b flex items-center gap-2.5 shrink-0",
            collapsed ? "justify-center px-0" : "px-4",
          )}
          style={{ borderColor: "var(--nav-border)" }}
        >
          <div className="shrink-0">
            <Logo size={28} />
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-bold text-[#e0eaf8] tracking-tight leading-none">
                Support RAG
              </div>
              <div className="text-[9px] font-bold text-primary tracking-[1.5px] uppercase mt-1">
                Admin
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 flex flex-col gap-px overflow-y-auto overflow-x-hidden">
          {NAV.filter((n) => !n.permission || hasPermission(n.permission)).map((item) => (
            <NavItem
              key={item.to}
              to={item.to}
              label={item.label}
              icon={item.icon}
              exact={item.exact}
              collapsed={collapsed}
            />
          ))}

          <div className="mt-auto pt-2">
            <hr
              className={cn("mb-2", collapsed ? "mx-1" : "mx-2")}
              style={{ borderColor: "var(--nav-border)" }}
            />
            <button
              onClick={toggleCollapsed}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className={cn(
                "flex items-center w-full py-2 text-[13px] font-medium rounded-r-lg",
                "border-l-2 border-l-transparent -ml-2 transition-colors",
                "text-nav-text hover:bg-white/5 hover:text-nav-text-hover",
                collapsed ? "justify-center px-3" : "gap-2.5 px-4",
              )}
            >
              <i
                aria-hidden="true"
                className={cn(
                  "ti text-sm shrink-0",
                  collapsed ? "ti-chevrons-right" : "ti-chevrons-left",
                )}
              />
              {!collapsed && <span className="flex-1">Collapse</span>}
            </button>
          </div>
        </nav>

        {/* User footer */}
        <div
          className="border-t shrink-0"
          style={{ borderColor: "var(--nav-border)" }}
        >
          {collapsed ? (
            <div className="flex flex-col items-center gap-2 py-3">
              <button
                onClick={() => void navigate("/profile")}
                title={user?.email ?? "Profile"}
                className="relative"
              >
                <Avatar name={user?.email ?? "?"} email={user?.email ?? ""} size={32} />
                <span className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-success border-2 border-[#1a2744]" />
              </button>
              <button
                onClick={() => void logout()}
                title="Sign out"
                className="text-nav-text hover:text-nav-text-hover transition-colors"
              >
                <i className="ti ti-logout text-sm" />
              </button>
            </div>
          ) : (
            <div className="px-3 py-2.5">
              <button
                onClick={() => void navigate("/profile")}
                className="group flex w-full items-center gap-3 rounded-lg px-1.5 py-1.5 transition-colors hover:bg-white/5"
              >
                <div className="relative shrink-0">
                  <Avatar name={user?.email ?? "?"} email={user?.email ?? ""} size={36} />
                  <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-success border-2 border-[#1a2744]" />
                </div>
                <div className="flex-1 min-w-0 text-left">
                  <div className="truncate text-[13px] font-semibold leading-tight text-[#e0eaf8]">
                    {user?.email?.split("@")[0] ?? "User"}
                  </div>
                  <div className="truncate text-[11px] text-nav-text leading-tight mt-0.5">
                    {user?.email ?? ""}
                  </div>
                </div>
                <i className="ti ti-chevron-right text-xs text-nav-text opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </button>
              <div className="mt-1 flex items-center gap-1 px-1.5">
                <span className="flex-1 truncate text-[10px] text-nav-text">
                  {user?.roles.join(", ") ?? "member"}
                </span>
                <button
                  onClick={() => void logout()}
                  title="Sign out"
                  className="text-nav-text hover:text-nav-text-hover transition-colors p-1 rounded"
                >
                  <i className="ti ti-logout text-sm" />
                </button>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 min-w-0 flex-col overflow-y-auto max-h-screen">
        {/* Top bar */}
        <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-border bg-card/90 px-6 backdrop-blur shrink-0">
          <span className="font-semibold text-sm md:hidden">Support RAG</span>
          <div className="flex-1" />
          <ConnectionBadge />
          <ThemeToggle />
          <button
            onClick={() => void navigate("/profile")}
            aria-label="My profile"
            className="rounded-full"
          >
            <Avatar name={user?.email ?? "?"} email={user?.email ?? ""} size={28} />
          </button>
        </header>

        {/* Page content */}
        <main className="mx-auto w-full max-w-[1100px] p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
