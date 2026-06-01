// Reset-password page (consumes ?token= from email link). Author: Al Amin Ahamed.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "@/api/auth";
import { useToast } from "@/components/ToastProvider";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { extractErrorMessage } from "@/lib/queryClient";

export function ResetPasswordPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const submit = useMutation({
    mutationFn: () => resetPassword({ token, password }),
    onSuccess: () => {
      toast.ok("Password updated. You can now sign in.");
      navigate("/login");
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  if (!token) {
    return (
      <AuthLayout title="Invalid link" description="This reset link is missing or malformed.">
        <p className="text-sm text-muted-foreground">
          <Link to="/forgot-password" className="text-primary underline-offset-4 hover:underline">
            Request a new reset link →
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Set a new password" description="Choose a strong password for your account.">
      <form
        className="space-y-1"
        onSubmit={(e) => {
          e.preventDefault();
          if (password !== confirm) {
            toast.err("Passwords don't match.");
            return;
          }
          submit.mutate();
        }}
      >
        <Field label="New password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min 8 characters"
            className="h-11 text-base"
            minLength={8}
            required
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
            minLength={8}
            required
          />
        </Field>

        <div className="pt-1">
          <Button type="submit" className="w-full h-11 text-sm font-semibold" disabled={submit.isPending}>
            {submit.isPending ? "Saving…" : "Set password"}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
}
