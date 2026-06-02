// Profile page: hero card + tabbed overview / security / permissions.
// Author: Al Amin Ahamed.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";
import { changePassword } from "@/api/auth";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/ToastProvider";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";

type ProfileContext = {
  user: NonNullable<ReturnType<typeof useAuth>["user"]>;
  refresh: () => Promise<void>;
};

const TABS = [
  { to: "overview", label: "Overview", icon: "ti-user" },
  { to: "security", label: "Security", icon: "ti-lock" },
  { to: "permissions", label: "Permissions", icon: "ti-shield" },
];

const RESOURCE_META: Record<string, { icon: string; color: string; bg: string; desc: string }> = {
  plugins:   { icon: "ti-puzzle",           color: "text-blue-500",   bg: "bg-blue-500/10",   desc: "Plugin management" },
  users:     { icon: "ti-users",            color: "text-violet-500", bg: "bg-violet-500/10", desc: "User management"   },
  settings:  { icon: "ti-settings",         color: "text-orange-500", bg: "bg-orange-500/10", desc: "System settings"   },
  queries:   { icon: "ti-search",           color: "text-green-500",  bg: "bg-green-500/10",  desc: "Query access"      },
  metrics:   { icon: "ti-chart-bar",        color: "text-teal-500",   bg: "bg-teal-500/10",   desc: "Analytics"         },
  ingestion: { icon: "ti-database-import",  color: "text-amber-600",  bg: "bg-amber-500/10",  desc: "Content ingestion" },
  feedback:  { icon: "ti-thumb-up",         color: "text-pink-500",   bg: "bg-pink-500/10",   desc: "Feedback"          },
};

const ACTION_LABELS: Record<string, string> = {
  read: "View",
  write: "Create & edit",
  delete: "Delete",
  invite: "Invite",
  trigger: "Trigger",
};

function memberDuration(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "1 day";
  if (days < 30) return `${days} days`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month" : `${months} months`;
}

function passwordStrength(pw: string): {
  score: number;
  label: string;
  barColor: string;
  labelColor: string;
} {
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^a-zA-Z0-9]/.test(pw)) s++;

  if (s <= 1) return { score: 1, label: "Weak",   barColor: "bg-destructive", labelColor: "text-destructive" };
  if (s === 2) return { score: 2, label: "Fair",   barColor: "bg-warning",     labelColor: "text-warning"     };
  if (s === 3) return { score: 3, label: "Good",   barColor: "bg-success",     labelColor: "text-success"     };
  return        { score: 4, label: "Strong", barColor: "bg-success",     labelColor: "text-success"     };
}

function detectSession(): { browser: string; os: string } {
  const ua = navigator.userAgent;
  const browser =
    ua.includes("Edg")     ? "Edge"    :
    ua.includes("Chrome")  ? "Chrome"  :
    ua.includes("Firefox") ? "Firefox" :
    ua.includes("Safari")  ? "Safari"  : "Browser";
  const os =
    ua.includes("Linux")   ? "Linux"   :
    ua.includes("Mac")     ? "macOS"   :
    ua.includes("Win")     ? "Windows" : "Unknown OS";
  return { browser, os };
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function ProfilePage() {
  const { user, refresh } = useAuth();
  if (!user) return null;

  const username = user.email.split("@")[0] ?? user.email;

  return (
    <div className="max-w-3xl space-y-6">
      {/* Hero card */}
      <div className="overflow-hidden rounded-xl border border-border">
        {/* Banner */}
        <div
          className="relative h-28"
          style={{ backgroundColor: "var(--nav)" }}
        >
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.05]"
            style={{
              backgroundImage:
                "radial-gradient(circle, #fff 1px, transparent 1px)",
              backgroundSize: "20px 20px",
            }}
          />
          <div className="pointer-events-none absolute -bottom-8 -right-8 size-40 rounded-full bg-indigo-500/20 blur-3xl" />
        </div>

        {/* Content */}
        <div className="bg-card px-6 pb-6">
          <div className="flex items-end justify-between -mt-10 mb-4">
            <div className="rounded-full ring-4 ring-card shadow">
              <Avatar name={user.email} email={user.email} size={80} />
            </div>
            <div className="flex items-center gap-2 mb-1">
              {user.roles.map((r) => (
                <Badge key={r} variant="accent">
                  {r.replace(/_/g, " ")}
                </Badge>
              ))}
              <Badge variant={user.is_active ? "success" : "secondary"}>
                <span
                  className={cn(
                    "mr-1 inline-block size-1.5 rounded-full",
                    user.is_active ? "bg-success" : "bg-muted-foreground",
                  )}
                />
                {user.is_active ? "Active" : "Inactive"}
              </Badge>
            </div>
          </div>

          <div className="mb-5">
            <h1 className="text-xl font-bold tracking-tight">{username}</h1>
            <p className="text-sm text-muted-foreground">{user.email}</p>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-3 divide-x divide-border overflow-hidden rounded-lg border border-border bg-muted/30">
            {[
              { label: "Member for", value: user.created_at ? memberDuration(user.created_at) : "—" },
              { label: "Permissions", value: String(user.permissions.length) },
              { label: "Roles",       value: String(user.roles.length) },
            ].map(({ label, value }) => (
              <div key={label} className="px-4 py-3 text-center">
                <p className="text-base font-bold tracking-tight">{value}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pill tabs */}
      <div className="flex w-fit gap-1 rounded-lg border border-border bg-muted/40 p-1">
        {TABS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all",
                isActive
                  ? "bg-card text-foreground shadow-sm border border-border"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
              )
            }
          >
            <i className={`ti ${icon} text-sm`} />
            {label}
          </NavLink>
        ))}
      </div>

      <Outlet context={{ user, refresh } satisfies ProfileContext} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-4 border-b border-border py-3.5 last:border-0 first:pt-0 last:pb-0">
      <span className="w-24 shrink-0 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60 mt-0.5">
        {label}
      </span>
      <span className={cn("flex-1 text-sm", mono && "font-mono text-[13px] text-muted-foreground")}>
        {value}
      </span>
    </div>
  );
}

export function ProfileOverview() {
  const { user } = useOutletContext<ProfileContext>();
  const [copied, setCopied] = useState(false);

  function copyId() {
    void navigator.clipboard?.writeText(user.id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const joinedDate = user.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "—";

  const byResource = user.permissions.reduce<Record<string, string[]>>((acc, p) => {
    const [res, action] = p.split(":");
    const key = res ?? "other";
    const label = action ? (ACTION_LABELS[action] ?? action) : p;
    (acc[key] ??= []).push(label);
    return acc;
  }, {});

  return (
    <div className="grid gap-5 md:grid-cols-2">
      {/* Account details */}
      <Card>
        <CardContent className="pt-5 pb-3">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <i className="ti ti-info-circle text-primary" /> Account details
          </h3>
          <div>
            <DetailRow label="Email" value={user.email} mono />
            <DetailRow
              label="User ID"
              value={
                <button
                  onClick={copyId}
                  className="group flex items-center gap-1.5 font-mono text-[12px] text-muted-foreground hover:text-foreground transition-colors"
                  title="Click to copy full ID"
                >
                  {user.id.slice(0, 13)}…
                  <i
                    className={cn(
                      "ti text-xs opacity-0 group-hover:opacity-100 transition-opacity",
                      copied ? "ti-check text-success" : "ti-copy",
                    )}
                  />
                  {copied && (
                    <span className="text-[10px] text-success">Copied!</span>
                  )}
                </button>
              }
            />
            <DetailRow
              label="Status"
              value={
                <span
                  className={cn(
                    "flex items-center gap-1.5 font-medium",
                    user.is_active ? "text-success" : "text-muted-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "inline-block size-1.5 rounded-full",
                      user.is_active ? "bg-success" : "bg-muted-foreground",
                    )}
                  />
                  {user.is_active ? "Active" : "Inactive"}
                </span>
              }
            />
            <DetailRow label="Joined" value={joinedDate} />
            <DetailRow
              label="Member"
              value={
                user.created_at
                  ? memberDuration(user.created_at)
                  : "—"
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* Access summary */}
      <Card>
        <CardContent className="pt-5 pb-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <i className="ti ti-shield text-primary" /> Access summary
          </h3>

          {/* Roles */}
          <div className="mb-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              Roles
            </p>
            {user.roles.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {user.roles.map((r) => (
                  <div
                    key={r}
                    className="flex items-center gap-1.5 rounded-md border border-border bg-muted/30 px-2.5 py-1.5"
                  >
                    <i className="ti ti-shield-half text-xs text-primary" />
                    <span className="text-xs font-semibold">{r.replace(/_/g, " ")}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No roles assigned</p>
            )}
          </div>

          {/* Permission breakdown */}
          <div className="border-t border-border pt-4">
            <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              Permissions by resource
            </p>
            {Object.keys(byResource).length === 0 ? (
              <p className="text-sm text-muted-foreground">No permissions</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(byResource)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([resource, actions]) => {
                    const meta = RESOURCE_META[resource];
                    return (
                      <div key={resource} className="flex items-center gap-2.5">
                        <div
                          className={cn(
                            "flex size-5 shrink-0 items-center justify-center rounded",
                            meta?.bg ?? "bg-muted",
                          )}
                        >
                          <i
                            className={cn(
                              `ti ${meta?.icon ?? "ti-circle"} text-[10px]`,
                              meta?.color ?? "text-muted-foreground",
                            )}
                          />
                        </div>
                        <span className="w-20 shrink-0 font-mono text-[11px] font-medium">
                          {resource}
                        </span>
                        <span className="min-w-0 truncate text-[11px] text-muted-foreground">
                          {actions.join(" · ")}
                        </span>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Security
// ---------------------------------------------------------------------------

export function ProfileSecurity() {
  const { user, refresh } = useOutletContext<ProfileContext>();
  const toast = useToast();
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw]         = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [showPw, setShowPw]       = useState(false);

  const strength = passwordStrength(newPw);
  const { browser, os } = detectSession();

  const change = useMutation({
    mutationFn: () => changePassword({ current_password: currentPw, new_password: newPw }),
    onSuccess: async () => {
      toast.ok("Password updated.");
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
      await refresh();
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (newPw !== confirmPw) { toast.err("Passwords don't match."); return; }
    change.mutate();
  }

  const checklist = [
    { label: "Password configured",  ok: true,                  desc: "Account has a password set",       disabled: false },
    { label: "Account active",        ok: user.is_active,        desc: "Account can log in",               disabled: false },
    { label: "Role assigned",         ok: user.roles.length > 0, desc: "At least one role is granted",     disabled: false },
    { label: "Permissions granted",   ok: user.permissions.length > 0, desc: "Access to resources",       disabled: false },
    { label: "Two-factor auth",       ok: false,                 desc: "Not yet available",                disabled: true  },
  ];

  const completedCount = checklist.filter((c) => c.ok && !c.disabled).length;
  const totalCount     = checklist.filter((c) => !c.disabled).length;

  return (
    <div className="grid gap-5 md:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        {/* Password change */}
        <Card>
          <CardContent className="pt-5 pb-5">
            <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
              <i className="ti ti-lock text-primary" /> Change password
            </h3>
            <p className="mb-4 text-xs text-muted-foreground">
              Minimum 8 characters. Updating logs out other sessions.
            </p>

            <form onSubmit={handleSubmit} className="space-y-3">
              <Field label="Current password">
                <div className="relative">
                  <Input
                    type={showPw ? "text" : "password"}
                    value={currentPw}
                    onChange={(e) => setCurrentPw(e.target.value)}
                    placeholder="••••••••"
                    required
                    autoComplete="current-password"
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((v) => !v)}
                    tabIndex={-1}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <i className={`ti ${showPw ? "ti-eye-off" : "ti-eye"} text-sm`} />
                  </button>
                </div>
              </Field>

              <Field label="New password">
                <Input
                  type={showPw ? "text" : "password"}
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  placeholder="Min 8 characters"
                  minLength={8}
                  required
                  autoComplete="new-password"
                />
                {newPw.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div className="flex gap-1">
                      {[0, 1, 2, 3].map((i) => (
                        <div
                          key={i}
                          className={cn(
                            "h-1 flex-1 rounded-full transition-colors",
                            i < strength.score ? strength.barColor : "bg-muted",
                          )}
                        />
                      ))}
                    </div>
                    <p className={cn("text-[11px] font-medium", strength.labelColor)}>
                      {strength.label}
                      {strength.score < 3 && (
                        <span className="ml-1.5 font-normal text-muted-foreground">
                          — try adding uppercase, numbers, or symbols
                        </span>
                      )}
                    </p>
                  </div>
                )}
              </Field>

              <Field label="Confirm new password">
                <Input
                  type={showPw ? "text" : "password"}
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  placeholder="Repeat password"
                  minLength={8}
                  required
                  autoComplete="new-password"
                />
                {confirmPw.length > 0 && newPw !== confirmPw && (
                  <p className="mt-1 text-[11px] text-destructive flex items-center gap-1">
                    <i className="ti ti-alert-circle" /> Passwords don't match
                  </p>
                )}
              </Field>

              <div className="pt-1">
                <Button
                  type="submit"
                  disabled={
                    change.isPending ||
                    !currentPw ||
                    newPw.length < 8 ||
                    newPw !== confirmPw
                  }
                >
                  {change.isPending ? "Saving…" : "Update password"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Active session */}
        <Card>
          <CardContent className="pt-5 pb-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold">
              <i className="ti ti-device-laptop text-primary" /> Active sessions
            </h3>
            <div className="flex items-start gap-4 rounded-lg border border-border bg-muted/20 p-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <i className="ti ti-device-laptop text-lg text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold">
                    {browser} on {os}
                  </p>
                  <Badge variant="success">This session</Badge>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{user.email}</p>
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {[
                    { icon: "ti-clock", label: "Access token · 15 min" },
                    { icon: "ti-refresh", label: "Refresh · 7 days" },
                    { icon: "ti-cookie", label: "HTTP-only cookie" },
                  ].map(({ icon, label }) => (
                    <span
                      key={label}
                      className="flex items-center gap-1 rounded border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground"
                    >
                      <i className={`ti ${icon} text-[10px]`} /> {label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Security checklist */}
      <div className="space-y-5">
        <Card>
          <CardContent className="pt-5 pb-5">
            <div className="mb-1 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <i className="ti ti-shield-check text-primary" /> Security
              </h3>
              <span className="text-xs font-semibold text-muted-foreground">
                {completedCount}/{totalCount}
              </span>
            </div>

            {/* Progress bar */}
            <div className="mb-4 mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-success transition-all"
                style={{ width: `${(completedCount / totalCount) * 100}%` }}
              />
            </div>

            <div className="space-y-3">
              {checklist.map((item) => (
                <div
                  key={item.label}
                  className={cn("flex items-start gap-3", item.disabled && "opacity-40")}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full",
                      item.ok
                        ? "bg-success/15 text-success"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    <i
                      className={cn(
                        "ti text-[10px] font-bold",
                        item.ok ? "ti-check" : "ti-x",
                      )}
                    />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <p className="text-sm font-medium leading-tight">{item.label}</p>
                      {item.disabled && (
                        <span className="rounded border border-border px-1 py-px text-[9px] uppercase tracking-wide text-muted-foreground">
                          soon
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-5 pb-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <i className="ti ti-key text-primary" /> Authentication
            </h3>
            <div className="space-y-2.5 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Method</span>
                <span className="font-medium">Email + password</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Cookie type</span>
                <Badge variant="outline" className="font-mono text-[10px]">HTTP-only</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Algorithm</span>
                <Badge variant="outline" className="font-mono text-[10px]">HS256 JWT</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Permissions
// ---------------------------------------------------------------------------

export function ProfilePermissions() {
  const { user } = useOutletContext<ProfileContext>();
  const { permissions, roles } = user;

  const groups = permissions.reduce<Record<string, { actions: string[]; perms: string[] }>>(
    (acc, perm) => {
      const [res, action] = perm.split(":");
      const key = res ?? "other";
      acc[key] ??= { actions: [], perms: [] };
      acc[key].actions.push(action ? (ACTION_LABELS[action] ?? action) : perm);
      acc[key].perms.push(perm);
      return acc;
    },
    {},
  );

  const sortedGroups = Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));

  if (sortedGroups.length === 0) {
    return (
      <Card className="max-w-xl">
        <CardContent className="py-12 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-xl bg-muted">
            <i className="ti ti-shield-off text-2xl text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">No permissions assigned</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Contact an administrator to request access.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="flex items-center gap-4 rounded-lg border border-border bg-muted/30 px-4 py-3">
        <div className="flex-1">
          <p className="text-sm font-semibold">
            {permissions.length} permission{permissions.length !== 1 ? "s" : ""}
            <span className="ml-2 font-normal text-muted-foreground">
              across {sortedGroups.length} resource{sortedGroups.length !== 1 ? "s" : ""}
            </span>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Inherited via{" "}
            {roles.length > 0 ? roles.map((r) => r.replace(/_/g, " ")).join(", ") : "direct grants"}
          </p>
        </div>
        <div className="flex gap-2">
          {sortedGroups.slice(0, 5).map(([res]) => {
            const meta = RESOURCE_META[res];
            return (
              <div
                key={res}
                title={meta?.desc ?? res}
                className={cn("flex size-7 items-center justify-center rounded-md", meta?.bg ?? "bg-muted")}
              >
                <i className={cn(`ti ${meta?.icon ?? "ti-circle"} text-sm`, meta?.color ?? "text-muted-foreground")} />
              </div>
            );
          })}
          {sortedGroups.length > 5 && (
            <div className="flex size-7 items-center justify-center rounded-md border border-border bg-muted text-[10px] font-bold text-muted-foreground">
              +{sortedGroups.length - 5}
            </div>
          )}
        </div>
      </div>

      {/* Group cards */}
      <div className="grid gap-3 sm:grid-cols-2">
        {sortedGroups.map(([resource, { perms }]) => {
          const meta = RESOURCE_META[resource];
          return (
            <Card key={resource} className="overflow-hidden">
              <CardContent className="pt-4 pb-4">
                <div className="mb-3 flex items-center gap-3">
                  <div
                    className={cn(
                      "flex size-9 shrink-0 items-center justify-center rounded-lg",
                      meta?.bg ?? "bg-muted",
                    )}
                  >
                    <i
                      className={cn(
                        `ti ${meta?.icon ?? "ti-circle"} text-base`,
                        meta?.color ?? "text-muted-foreground",
                      )}
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold leading-tight capitalize">
                      {resource.replace(/_/g, " ")}
                    </p>
                    <p className="text-[11px] text-muted-foreground">{meta?.desc ?? resource}</p>
                  </div>
                  <span className="ml-auto shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
                    {perms.length}
                  </span>
                </div>

                <div className="space-y-1.5">
                  {perms.map((perm) => {
                    const [, action] = perm.split(":");
                    const actionLabel = action ? (ACTION_LABELS[action] ?? action) : perm;
                    return (
                      <div key={perm} className="flex items-center gap-2.5">
                        <div
                          className={cn(
                            "flex size-4 shrink-0 items-center justify-center rounded",
                            meta?.bg ?? "bg-muted",
                          )}
                        >
                          <i className={cn("ti ti-check text-[9px]", meta?.color ?? "text-muted-foreground")} />
                        </div>
                        <span className="flex-1 text-xs font-medium">{actionLabel}</span>
                        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                          {perm}
                        </code>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
