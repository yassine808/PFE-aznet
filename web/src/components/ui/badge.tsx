import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-ring",
  {
    variants: {
      variant: {
        default: "border-transparent bg-cardhi text-ink",
        secondary: "border-line bg-transparent text-muted",
        // level chips in the Logs table
        info: "border-transparent bg-cardhi text-muted",
        warn: "border-transparent bg-accent/15 text-accent",
        error: "border-transparent bg-down/15 text-down",
        success: "border-transparent bg-up/15 text-up",
        outline: "border-line text-ink",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
