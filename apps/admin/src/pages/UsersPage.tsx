// Users management page: list users, invite, add, deactivate, delete.
// Author: Al Amin Ahamed.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createUser,
  deleteUser,
  inviteUser,
  listRoles,
  listUsers,
  patchUser,
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

export function UsersPage() {
  const { hasPermission } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [showInvite, setShowInvite] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });

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

      {showInvite && (
        <InviteModal
          roles={roles.data ?? []}
          onClose={() => setShowInvite(false)}
          onSuccess={() => { setShowInvite(false); void qc.invalidateQueries({ queryKey: ["users"] }); }}
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

  const invite = useMutation({
    mutationFn: () => inviteUser({ email: email.trim(), role_id: roleId }),
    onSuccess: (data) => {
      toast.ok(data.invite_url ? `Invite URL: ${data.invite_url}` : `Token: ${data.token}`);
      onSuccess();
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <h2 className="text-lg font-semibold">Invite user</h2>
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
