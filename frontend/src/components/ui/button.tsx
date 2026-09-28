import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { ShimmerButton } from "@/components/godui/shimmer-button";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const SIZES: Record<Size, string> = {
  sm: "min-h-9 px-3 py-1.5 text-meta gap-1.5",
  md: "min-h-10 px-3.5 py-2 text-body gap-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", className, type = "button", ...props },
  ref,
) {
  return (
    <ShimmerButton ref={ref} type={type} variant={variant} size={size} shimmer={variant === "primary"}
      contentClassName="contents" className={cn(SIZES[size], className)} {...props} />
  );
});
