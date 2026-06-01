// Forgot-password page. Author: Al Amin Ahamed.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "@/api/auth";
import { useToast } from "@/components/ToastProvider";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { extractErrorMessage } from "@/lib/queryClient";

export function ForgotPasswordPage() {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const submit = useMutation({
    mutationFn: () => forgotPassword({ email: email.trim() }),
    onSuccess: () => setSent(true),
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  if (sent) {
    return (
      <AuthLayout title="Check your inbox" description="A reset link is on its way.">
        <div className="space-y-5">
          <div className="rounded-xl border border-border/60 bg-muted/40 px-5 py-5 space-y-1.5">
            <p className="text-sm font-medium">Email sent to</p>
            <p className="text-sm font-mono text-muted-foreground break-all">{email}</p>
            <p className="text-xs text-muted-foreground pt-1 leading-relaxed">
              Check your inbox and spam folder. The link expires in 1 hour.
            </p>
          </div>
          <Link
            to="/login"
            className="block text-center text-sm text-primary underline-offset-4 hover:underline transition-colors"
          >
            ← Back to sign in
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter your email and we'll send you a reset link."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="h-11 text-base"
            required
            autoFocus
          />
        </Field>

        <div className="pt-1 space-y-3">
          <Button type="submit" className="w-full h-11 text-sm font-semibold" disabled={submit.isPending}>
            {submit.isPending ? "Sending…" : "Send reset link"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            <Link
              to="/login"
              className="text-primary underline-offset-4 hover:underline transition-colors"
            >
              ← Back to sign in
            </Link>
          </p>
        </div>
      </form>
    </AuthLayout>
  );
}
