// Users management page: list users, invites, invite, add, deactivate, delete.
// Author: Al Amin Ahamed.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createUser,
  deleteUser,
  inviteUser,
  listInvites,
  listRoles,
  listUsers,
  patchUser,
  regenerateInvite,
} from "@/api/auth";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/ToastProvider";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/feedback";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { extractErrorMessage } from "@/lib/queryClient";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { InviteSummary } from "@/types/api";

// ── Status helpers ──────────────────────────────────────────────────────────

const INVITE_STATUS_STYLE: Record<string, { cls: string; label: string }> = {
  pending: {
    cls: "bg-warning/10 text-warning border-warning/20",
    label: "Pending",
  },
  expired: {
    cls: "bg-muted text-muted-foreground border-border",
    label: "Expired",
  },
  accepted: {
    cls: "bg-success/10 text-success border-success/20",
    label: "Accepted",
  },
};

function StatusPill({ status }: { status: string }) {
  const s = (INVITE_STATUS_STYLE[status] ?? INVITE_STATUS_STYLE.expired)!;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        s.cls,
      )}
    >
      {s.label}
    </span>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export function UsersPage() {
  const { hasPermission } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [showInvite, setShowInvite] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [search, setSearch] = useState("");

  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const invites = useQuery({ queryKey: ["invites"], queryFn: listInvites });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      patchUser(id, { is_active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const removeUser = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] });
      toast.ok("User deleted.");
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const regenInvite = useMutation({
    mutationFn: (id: string) => regenerateInvite(id),
    onSuccess: async (data) => {
      void qc.invalidateQueries({ queryKey: ["invites"] });
      const url =
        data.invite_url ??
        `${window.location.origin}/accept-invite?token=${data.token}`;
      try {
        await navigator.clipboard.writeText(url);
        toast.ok("New invite link copied to clipboard.");
      } catch {
        toast.ok(`Invite link: ${url}`);
      }
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const canWrite = hasPermission("users:write");
  const canInvite = hasPermission("users:invite");

  // Derived stats
  const allUsers = users.data ?? [];
  const activeCount = allUsers.filter((u) => u.is_active).length;
  const inactiveCount = allUsers.filter((u) => !u.is_active).length;
  const pendingCount = (invites.data ?? []).filter((i) => i.status === "pending").length;

  const q = search.trim().toLowerCase();
  const filteredUsers = q
    ? allUsers.filter(
        (u) =>
          u.email.toLowerCase().includes(q) ||
          u.roles.some((r) => r.toLowerCase().includes(q)),
      )
    : allUsers;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Users"
        description="Manage admin-console accounts and invitations."
      />

      {/* ── Stats bar ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          icon="ti-users"
          label="Total users"
          value={users.isLoading ? "—" : allUsers.length}
        />
        <StatCard
          icon="ti-user-check"
          label="Active"
          value={users.isLoading ? "—" : activeCount}
          tone="success"
        />
        <StatCard
          icon="ti-user-off"
          label="Inactive"
          value={users.isLoading ? "—" : inactiveCount}
          tone={inactiveCount > 0 ? "warning" : "default"}
        />
        <StatCard
          icon="ti-mail"
          label="Pending invites"
          value={invites.isLoading ? "—" : pendingCount}
          tone={pendingCount > 0 ? "warning" : "default"}
        />
      </div>

      {/* ── Accounts table ─────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 flex-wrap">
          <CardTitle>Accounts</CardTitle>
          <div className="flex flex-1 items-center gap-2 min-w-0">
            <div className="relative flex-1 max-w-xs">
              <i className="ti ti-search absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-[13px]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter by email or role…"
                className="pl-7 h-8 text-sm"
              />
            </div>
            <div className="flex shrink-0 gap-2">
              {canInvite && (
                <Button variant="secondary" onClick={() => setShowInvite(true)}>
                  <i className="ti ti-mail-plus mr-1.5 text-[13px]" />
                  Invite user
                </Button>
              )}
              {canWrite && (
                <Button onClick={() => setShowAdd(true)}>
                  <i className="ti ti-user-plus mr-1.5 text-[13px]" />
                  Add user
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {users.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : users.isError ? (
            <ErrorState message={extractErrorMessage(users.error)} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Roles</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Threads</TableHead>
                  <TableHead>Joined</TableHead>
                  {canWrite && <TableHead className="text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={canWrite ? 6 : 5}
                      className="text-center text-sm text-muted-foreground py-6"
                    >
                      {q ? "No users match your filter." : "No users yet."}
                    </TableCell>
                  </TableRow>
                )}
                {filteredUsers.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="flex items-center gap-2.5 min-w-0">
                        <Avatar email={u.email} name={u.email} size={28} className="shrink-0" />
                        <span className="font-mono text-sm truncate">{u.email}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {u.roles.length > 0 ? (
                          u.roles.map((r) => (
                            <Badge key={r} variant="secondary" className="text-[11px]">
                              {r}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </div>
                      {u.permissions.length > 0 && (
                        <p
                          className="text-[10px] text-muted-foreground mt-0.5 cursor-default"
                          title={u.permissions.join(", ")}
                        >
                          {u.permissions.length} permission{u.permissions.length !== 1 ? "s" : ""}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                          u.is_active
                            ? "bg-success/10 text-success border-success/20"
                            : "bg-muted text-muted-foreground border-border",
                        )}
                      >
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums text-muted-foreground">
                      {u.thread_count > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <i className="ti ti-messages text-[11px]" />
                          {u.thread_count}
                        </span>
                      ) : (
                        <span className="text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {relativeTime(u.created_at)}
                    </TableCell>
                    {canWrite && (
                      <TableCell className="text-right">
                        {confirmDeleteId === u.id ? (
                          <span className="inline-flex items-center gap-1.5 text-[11px]">
                            <span className="text-destructive font-medium">Delete?</span>
                            <button
                              type="button"
                              onClick={() => {
                                removeUser.mutate(u.id);
                                setConfirmDeleteId(null);
                              }}
                              disabled={removeUser.isPending}
                              className="text-destructive font-semibold hover:underline disabled:opacity-50"
                            >
                              Yes
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmDeleteId(null)}
                              className="text-muted-foreground hover:underline"
                            >
                              No
                            </button>
                          </span>
                        ) : (
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              onClick={() =>
                                toggleActive.mutate({
                                  id: u.id,
                                  is_active: !u.is_active,
                                })
                              }
                              disabled={
                                toggleActive.isPending &&
                                (toggleActive.variables as { id: string })?.id === u.id
                              }
                            >
                              {u.is_active ? "Deactivate" : "Activate"}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                              title="Delete user"
                              onClick={() => setConfirmDeleteId(u.id)}
                            >
                              <i className="ti ti-trash text-[12px]" />
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Invites table ──────────────────────────────────────────────── */}
      {canInvite && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Invitations</CardTitle>
            <span className="text-xs text-muted-foreground">
              {invites.data
                ? `${pendingCount} pending`
                : ""}
            </span>
          </CardHeader>
          <CardContent>
            {invites.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : invites.isError ? (
              <ErrorState message={extractErrorMessage(invites.error)} />
            ) : !invites.data?.length ? (
              <p className="text-sm text-muted-foreground">No invitations sent yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Sent</TableHead>
                    <TableHead>Expires / Accepted</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invites.data.map((inv) => (
                    <InviteRow
                      key={inv.id}
                      invite={inv}
                      onResend={() => regenInvite.mutate(inv.id)}
                      loading={
                        regenInvite.isPending && regenInvite.variables === inv.id
                      }
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Modals ─────────────────────────────────────────────────────── */}
      {showInvite && (
        <InviteModal
          roles={roles.data ?? []}
          onClose={() => setShowInvite(false)}
          onSuccess={() => {
            setShowInvite(false);
            void qc.invalidateQueries({ queryKey: ["users"] });
            void qc.invalidateQueries({ queryKey: ["invites"] });
          }}
        />
      )}
      {showAdd && (
        <AddUserModal
          roles={roles.data ?? []}
          onClose={() => setShowAdd(false)}
          onSuccess={() => {
            setShowAdd(false);
            void qc.invalidateQueries({ queryKey: ["users"] });
          }}
        />
      )}
    </div>
  );
}

// ── InviteRow ───────────────────────────────────────────────────────────────

function InviteRow({
  invite,
  onResend,
  loading,
}: {
  invite: InviteSummary;
  onResend: () => void;
  loading: boolean;
}) {
  return (
    <TableRow>
      <TableCell className="font-mono text-sm">{invite.email}</TableCell>
      <TableCell>
        {invite.role_name ? (
          <Badge variant="secondary" className="text-[11px]">
            {invite.role_name}
          </Badge>
        ) : (
          <span className="text-muted-foreground text-xs">—</span>
        )}
      </TableCell>
      <TableCell>
        <StatusPill status={invite.status} />
      </TableCell>
      <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
        {relativeTime(invite.created_at)}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
        {invite.status === "accepted" && invite.used_at
          ? relativeTime(invite.used_at)
          : relativeTime(invite.expires_at)}
      </TableCell>
      <TableCell className="text-right">
        {invite.status !== "accepted" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onResend}
            disabled={loading}
            title="Regenerate and copy invite link"
            className="h-7 gap-1.5 px-2 text-xs"
          >
            <i className="ti ti-send text-[12px]" />
            Resend
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

// ── InviteModal ─────────────────────────────────────────────────────────────

function InviteModal({
  roles,
  onClose,
  onSuccess,
}: {
  roles: { id: string; name: string }[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState(roles[0]?.id ?? "");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const invite = useMutation({
    mutationFn: () => inviteUser({ email: email.trim(), role_id: roleId }),
    onSuccess: (data) => {
      const url =
        data.invite_url ??
        `${window.location.origin}/accept-invite?token=${data.token}`;
      setInviteUrl(url);
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  async function copyLink() {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.ok(`Invite link: ${inviteUrl}`);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <h2 className="text-lg font-semibold">Invite user</h2>
        {inviteUrl ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Invite created. Copy the link and share it with the user.
            </p>
            <div className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">
                {inviteUrl}
              </span>
              <Button
                size="sm"
                variant="secondary"
                onClick={copyLink}
                className="shrink-0"
              >
                {copied ? (
                  <i className="ti ti-check text-success" />
                ) : (
                  <i className="ti ti-copy" />
                )}
              </Button>
            </div>
            <div className="flex justify-end">
              <Button onClick={onSuccess}>Done</Button>
            </div>
          </div>
        ) : (
          <>
            <Field label="Email">
              <Input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                type="email"
              />
            </Field>
            <Field label="Role">
              <Select value={roleId} onValueChange={setRoleId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {roles.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button
                onClick={() => invite.mutate()}
                disabled={!email || !roleId || invite.isPending}
              >
                {invite.isPending ? "Sending…" : "Send invite"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── AddUserModal ────────────────────────────────────────────────────────────

function AddUserModal({
  roles,
  onClose,
  onSuccess,
}: {
  roles: { id: string; name: string }[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState(roles[0]?.id ?? "");

  const add = useMutation({
    mutationFn: () =>
      createUser({ email: email.trim(), password, role_ids: roleId ? [roleId] : [] }),
    onSuccess: () => {
      toast.ok("User created.");
      onSuccess();
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <h2 className="text-lg font-semibold">Add user</h2>
        <Field label="Email">
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            type="email"
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min 8 characters"
          />
        </Field>
        <Field label="Role">
          <Select value={roleId} onValueChange={setRoleId}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {roles.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => add.mutate()}
            disabled={!email || password.length < 8 || !roleId || add.isPending}
          >
            {add.isPending ? "Creating…" : "Create user"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
