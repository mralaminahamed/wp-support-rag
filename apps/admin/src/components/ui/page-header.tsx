// Consistent page header (title + optional actions). Author: Al Amin Ahamed.
import type { ReactNode } from "react";

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex min-h-9 items-center justify-between gap-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}
