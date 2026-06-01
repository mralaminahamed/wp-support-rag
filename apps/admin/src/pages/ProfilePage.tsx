// Logged-in user's profile: overview, security, permissions sub-routes.
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
import { PageHeader } from "@/components/ui/page-header";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";

type ProfileContext = {
  user: NonNullable<ReturnType<typeof useAuth>["user"]>;
  refresh: () => Promise<void>;
};

const TABS = [
  { to: "overview", label: "Overview" },
  { to: "security", label: "Security" },
  { to: "permissions", label: "Permissions" },
];

export function ProfilePage() {
  const { user, refresh } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-5">
      <PageHeader title="My Profile" description="Account details and security settings." />

      <div className="flex border-b border-border">
        {TABS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors cursor-pointer",
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )
            }
          >
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

export function ProfileOverview() {
  const { user } = useOutletContext<ProfileContext>();

  const joinedDate = user.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "—";

  return (
    <div className="grid gap-5 md:grid-cols-[260px_1fr]">
      <Card className="overflow-hidden">
        <div
          className="h-20 w-full"
          style={{ background: "linear-gradient(135deg, #4338ca 0%, #6d28d9 50%, #7c3aed 100%)" }}
        />
        <CardContent className="flex flex-col items-center gap-3 px-6 pb-7 pt-0 text-center -mt-9">
          <div className="ring-4 ring-card rounded-full shadow-sm">
            <Avatar name={user.email} email={user.email} size={68} />
          </div>
          <div className="mt-1">
            <p className="text-sm font-semibold break-all leading-snug">{user.email}</p>
            <p className="mt-1 text-[11px] font-mono text-muted-foreground tracking-wide">
              {user.id.slice(0, 8).toUpperCase()}
            </p>
          </div>
          <Badge variant={user.is_active ? "success" : "secondary"} className="mt-0.5">
            {user.is_active ? "● Active" : "○ Inactive"}
          </Badge>
          {user.roles.length > 0 && (
            <div className="flex flex-wrap justify-center gap-1 mt-1">
              {user.roles.map((r) => (
                <Badge key={r} variant="accent" className="text-xs">{r}</Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-0 pb-0">
          <DetailRow label="Email" value={user.email} mono />
          <DetailRow label="Member since" value={joinedDate} />
          <DetailRow label="Account status" value={user.is_active ? "Active" : "Inactive"} />
          <DetailRow
            label="Roles"
            value={
              user.roles.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {user.roles.map((r) => (
                    <Badge key={r} variant="accent">{r}</Badge>
                  ))}
                </div>
              ) : (
                <span className="text-muted-foreground">No roles assigned</span>
              )
            }
          />
          <DetailRow
            label="Permissions"
            value={
              <span className="text-muted-foreground">
                {user.permissions.length} permission{user.permissions.length !== 1 ? "s" : ""}
              </span>
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}

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
    <div className="flex items-start gap-6 py-4 border-b border-border last:border-0 first:pt-5 last:pb-5">
      <span className="w-28 shrink-0 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60 mt-0.5">
        {label}
      </span>
      <span className={cn("flex-1 text-sm", mono && "font-mono text-muted-foreground")}>{value}</span>
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
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");

  const change = useMutation({
    mutationFn: () => changePassword({ current_password: currentPw, new_password: newPw }),
    onSuccess: async () => {
      toast.ok("Password updated.");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      await refresh();
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (newPw !== confirmPw) {
      toast.err("New passwords don't match.");
      return;
    }
    change.mutate();
  }

  return (
    <div className="max-w-md space-y-4">
      <Card>
        <CardContent className="pt-5 pb-5">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">Change password</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Must be at least 8 characters.</p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-3">
            <Field label="Current password">
              <Input
                type="password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                placeholder="••••••••"
                required
                autoFocus
              />
            </Field>
            <Field label="New password">
              <Input
                type="password"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                placeholder="Min 8 characters"
                minLength={8}
                required
              />
            </Field>
            <Field label="Confirm new password">
              <Input
                type="password"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                placeholder="Repeat new password"
                minLength={8}
                required
              />
            </Field>
            <div className="pt-1">
              <Button type="submit" disabled={change.isPending || !currentPw || newPw.length < 8}>
                {change.isPending ? "Saving…" : "Update password"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-5 pb-5">
          <h3 className="text-sm font-semibold mb-3">Session</h3>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Signed in as</span>
              <span className="font-mono text-xs text-foreground">{user.email}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Access token</span>
              <span className="text-xs text-muted-foreground">15 min TTL</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Session cookie</span>
              <span className="text-xs text-muted-foreground">7 day TTL · auto-refresh</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Permissions
// ---------------------------------------------------------------------------

export function ProfilePermissions() {
  const { user } = useOutletContext<ProfileContext>();
  const { permissions } = user;

  const groups = permissions.reduce<Record<string, string[]>>((acc, perm) => {
    const group = perm.includes(":") ? (perm.split(":")[0] ?? "other") : "other";
    (acc[group] ??= []).push(perm);
    return acc;
  }, {});

  const sortedGroups = Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));

  if (sortedGroups.length === 0) {
    return (
      <Card className="max-w-xl">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No permissions assigned.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="max-w-xl space-y-3">
      <p className="text-xs text-muted-foreground">
        {permissions.length} permission{permissions.length !== 1 ? "s" : ""} across {sortedGroups.length} group{sortedGroups.length !== 1 ? "s" : ""}
      </p>
      {sortedGroups.map(([group, perms]) => (
        <Card key={group}>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                {group}
              </h3>
              <span className="text-[10px] font-medium text-muted-foreground bg-muted rounded-full px-2 py-0.5">
                {perms.length}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {perms.map((p) => (
                <Badge key={p} variant="outline" className="font-mono text-[11px] tracking-tight">
                  {p}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
