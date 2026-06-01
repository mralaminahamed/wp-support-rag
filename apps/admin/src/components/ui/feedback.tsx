// Spinner, empty/error states. Author: Al Amin Ahamed.
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block size-4 animate-spin rounded-full border-2 border-current/30 border-t-current",
        className,
      )}
      aria-label="loading"
    />
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
      <i className="ti ti-inbox text-3xl opacity-50" />
      <p className="font-medium text-foreground text-sm">{title}</p>
      {hint && <p className="text-sm">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
      <i className="ti ti-alert-circle text-base shrink-0" />
      <span>{message}</span>
    </div>
  );
}
