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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/feedback";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractErrorMessage } from "@/lib/queryClient";
import { relativeTime } from "@/lib/format";
import type { InviteSummary } from "@/types/api";

const INVITE_STATUS_VARIANT: Record<string, "accent" | "secondary" | "success"> = {
  pending: "accent",
  expired: "secondary",
  accepted: "success",
};

export function UsersPage() {
  const { hasPermission } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [showInvite, setShowInvite] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const invites = useQuery({ queryKey: ["invites"], queryFn: listInvites });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      patchUser(id, { is_active }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["users"] }); },
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
      const url = data.invite_url ?? `${window.location.origin}/accept-invite?token=${data.token}`;
      try {
        await navigator.clipboard.writeText(url);
        toast.ok("Invite link copied to clipboard.");
      } catch {
        toast.ok(`Invite link: ${url}`);
      }
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const canWrite = hasPermission("users:write");
  const canInvite = hasPermission("users:invite");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Users"
        description="Manage admin-console accounts and roles."
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Accounts</CardTitle>
          <div className="flex gap-2">
            {canInvite && (
              <Button variant="secondary" onClick={() => setShowInvite(true)}>
                Invite user
              </Button>
            )}
            {canWrite && (
              <Button onClick={() => setShowAdd(true)}>Add user</Button>
            )}
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
                  <TableHead>Email</TableHead>
                  <TableHead>Roles</TableHead>
                  <TableHead>Status</TableHead>
                  {canWrite && <TableHead>Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.data?.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-mono text-sm">{u.email}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {u.roles.map((r) => (
                          <Badge key={r} variant="secondary">{r}</Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.is_active ? "accent" : "secondary"}>
                        {u.is_active ? "active" : "inactive"}
                      </Badge>
                    </TableCell>
                    {canWrite && (
                      <TableCell>
                        <div className="flex gap-2">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => toggleActive.mutate({ id: u.id, is_active: !u.is_active })}
                          >
                            {u.is_active ? "Deactivate" : "Activate"}
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              if (confirm(`Delete ${u.email}?`)) removeUser.mutate(u.id);
                            }}
                          >
                            Delete
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {canInvite && (
        <Card>
          <CardHeader>
            <CardTitle>Invites</CardTitle>
          </CardHeader>
          <CardContent>
            {invites.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : invites.isError ? (
              <ErrorState message={extractErrorMessage(invites.error)} />
            ) : !invites.data?.length ? (
              <p className="text-sm text-muted-foreground">No invites sent yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invites.data.map((inv) => (
                    <InviteRow
                      key={inv.id}
                      invite={inv}
                      onCopyLink={() => regenInvite.mutate(inv.id)}
                      loading={regenInvite.isPending && regenInvite.variables === inv.id}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

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
          onSuccess={() => { setShowAdd(false); void qc.invalidateQueries({ queryKey: ["users"] }); }}
        />
      )}
    </div>
  );
}

function InviteRow({
  invite,
  onCopyLink,
  loading,
}: {
  invite: InviteSummary;
  onCopyLink: () => void;
  loading: boolean;
}) {
  return (
    <TableRow>
      <TableCell className="font-mono text-sm">{invite.email}</TableCell>
      <TableCell>
        {invite.role_name ? (
          <Badge variant="secondary">{invite.role_name}</Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <Badge variant={INVITE_STATUS_VARIANT[invite.status] ?? "secondary"}>
          {invite.status}
        </Badge>
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {invite.status === "accepted" && invite.used_at
          ? `accepted ${relativeTime(invite.used_at)}`
          : relativeTime(invite.expires_at)}
      </TableCell>
      <TableCell>
        {invite.status !== "accepted" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onCopyLink}
            disabled={loading}
            title="Regenerate and copy invite link"
            className="h-7 gap-1.5 px-2 text-xs"
          >
            <i className="ti ti-copy text-[12px]" />
            Copy link
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

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
      const url = data.invite_url ?? `${window.location.origin}/accept-invite?token=${data.token}`;
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
            <p className="text-sm text-muted-foreground">Invite created. Copy the link and share it with the user.</p>
            <div className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{inviteUrl}</span>
              <Button size="sm" variant="secondary" onClick={copyLink} className="shrink-0">
                {copied ? <i className="ti ti-check text-success" /> : <i className="ti ti-copy" />}
              </Button>
            </div>
            <div className="flex justify-end">
              <Button onClick={onSuccess}>Done</Button>
            </div>
          </div>
        ) : (
          <>
            <Field label="Email">
              <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com" />
            </Field>
            <Field label="Role">
              <Select value={roleId} onValueChange={setRoleId}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button onClick={() => invite.mutate()} disabled={!email || !roleId || invite.isPending}>
                {invite.isPending ? "Sending…" : "Send invite"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

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
    onSuccess: () => { toast.ok("User created."); onSuccess(); },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <h2 className="text-lg font-semibold">Add user</h2>
        <Field label="Email">
          <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com" />
        </Field>
        <Field label="Password">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min 8 characters" />
        </Field>
        <Field label="Role">
          <Select value={roleId} onValueChange={setRoleId}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
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
