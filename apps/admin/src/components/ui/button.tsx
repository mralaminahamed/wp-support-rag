// Button primitive (cva + Tailwind). Author: Al Amin Ahamed.
import { type VariantProps, cva } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:opacity-55 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-accent-soft",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-fg hover:brightness-110",
        secondary: "border border-border bg-surface text-fg hover:bg-surface-2",
        ghost: "text-muted hover:bg-surface-2 hover:text-fg",
        danger: "bg-err text-white hover:brightness-110",
      },
      size: { md: "h-9 px-4 text-sm", sm: "h-8 px-3 text-[13px]", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(button({ variant, size }), className)} {...props} />;
}
