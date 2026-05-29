// Compact metric/status tile. Author: Al Amin Ahamed.
import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatCard({
  icon: Icon,
  label,
  value,
  tone = "default",
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
  tone?: "default" | "success" | "warning" | "destructive";
}) {
  const toneClass = {
    default: "text-muted-foreground",
    success: "text-success",
    warning: "text-warning",
    destructive: "text-destructive",
  }[tone];

  return (
    <div className="rounded-lg border bg-muted/30 p-4">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-muted-foreground">{label}</span>
        <Icon className={cn("size-4", toneClass)} />
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}
