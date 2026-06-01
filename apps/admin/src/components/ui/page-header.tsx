// Consistent page header (title + optional description + actions). Author: Al Amin Ahamed.
import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-3">
      <div>
        <h2 className="text-[1.05rem] font-bold tracking-tight text-text-1">{title}</h2>
        {description && (
          <p className="mt-0.5 text-sm text-text-3">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}
