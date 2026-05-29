// Card primitives. Author: Al Amin Ahamed.
import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[12px] border border-border bg-surface shadow-sm", className)}
      {...props}
    />
  );
}

export function CardHead({
  title,
  actions,
}: {
  title: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      {actions}
    </div>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />;
}
