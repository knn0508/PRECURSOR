import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider",
  {
    variants: {
      variant: {
        neutral: "border-line bg-surface-2 text-ink-muted",
        demo: "border-warn/40 bg-warn/10 text-warn",
        ok: "border-ok/40 bg-ok/10 text-ok",
        accent: "border-accent/40 bg-accent/10 text-accent",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
