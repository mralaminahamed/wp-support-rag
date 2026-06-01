// Accept an invite token and set a password to create an account.
// Author: Al Amin Ahamed.
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { acceptInvite } from "@/api/auth";
import { useAuth } from "@/lib/auth";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { extractErrorMessage } from "@/lib/queryClient";

export function AcceptInvitePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("Invalid invite link — token is missing.");
      return;
    }
    setLoading(true);
    try {
      await acceptInvite({ token, password });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2">
          <Logo size={36} />
          <h1 className="text-xl font-bold">Accept invitation</h1>
          <p className="text-sm text-muted-foreground">Set a password to create your account.</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Password">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 8 characters"
              required
              minLength={8}
              autoFocus
            />
          </Field>
          <Field label="Confirm password">
            <Input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat password"
              required
            />
          </Field>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading || !token}>
            {loading ? "Creating account…" : "Create account"}
          </Button>
        </form>
      </div>
    </div>
  );
}
