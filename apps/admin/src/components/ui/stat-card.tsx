// Compact metric tile. Author: Al Amin Ahamed.
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatCard({
  icon,
  label,
  value,
  hint,
  tone = "default",
  children,
}: {
  icon: string;
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "success" | "warning" | "destructive";
  children?: ReactNode;
}) {
  const toneClass = {
    default: "text-primary",
    success: "text-success",
    warning: "text-warning",
    destructive: "text-destructive",
  }[tone];

  return (
    <div className="rounded-[10px] border border-border bg-card p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-[11px] font-semibold text-text-3 uppercase tracking-wide">
          {label}
        </span>
        <i className={cn(`ti ${icon} text-base`, toneClass)} />
      </div>
      <p className="text-2xl font-bold text-text-1 leading-tight">{value}</p>
      {hint && <p className="text-[11px] text-text-4 mt-1">{hint}</p>}
      {children}
    </div>
  );
}
