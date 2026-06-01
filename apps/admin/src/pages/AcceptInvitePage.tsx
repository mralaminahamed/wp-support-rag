// Accept an invite token and set a password to create an account.
// Author: Al Amin Ahamed.
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { acceptInvite } from "@/api/auth";
import { useAuth } from "@/lib/auth";
import { AuthLayout } from "@/components/layout/AuthLayout";
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
    <AuthLayout
      title="Accept invitation"
      description="Set a password to activate your account."
    >
      <form onSubmit={handleSubmit} className="space-y-1">
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min 8 characters"
            className="h-11 text-base"
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
            className="h-11 text-base"
            required
          />
        </Field>

        {error && (
          <div className="flex items-start gap-2.5 rounded-lg bg-destructive/10 border border-destructive/20 px-3.5 py-3">
            <span className="mt-0.5 shrink-0 text-destructive text-xs">✕</span>
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        <div className="pt-1">
          <Button type="submit" className="w-full h-11 text-sm font-semibold" disabled={loading || !token}>
            {loading ? "Creating account…" : "Create account"}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
}
