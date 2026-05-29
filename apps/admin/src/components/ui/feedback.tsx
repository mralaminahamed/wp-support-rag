// Spinner, skeleton, empty/error states. Author: Al Amin Ahamed.
import { AlertCircle, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-accent-soft border-t-accent",
        className,
      )}
      style={{ animationName: "spin" }}
      aria-label="loading"
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-md", className)} />;
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center text-muted">
      <Inbox className="h-7 w-7 opacity-60" />
      <p className="font-medium text-fg">{title}</p>
      {hint && <p className="text-sm">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-err-soft px-3 py-2.5 text-sm text-err">
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
