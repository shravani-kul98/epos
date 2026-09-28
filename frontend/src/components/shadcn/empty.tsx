// Adapted from shadcn/ui's MIT-licensed Empty composition; see LICENSE.txt.
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export function Empty({ className, ...props }: ComponentProps<"div">): JSX.Element {
  return <div data-slot="empty" className={cn("flex min-w-0 flex-col items-center justify-center gap-6 rounded-card p-6 text-center md:p-12", className)} {...props} />;
}

export function EmptyHeader({ className, ...props }: ComponentProps<"div">): JSX.Element {
  return <div data-slot="empty-header" className={cn("flex max-w-md flex-col items-center gap-2 text-center", className)} {...props} />;
}

export function EmptyMedia({ className, ...props }: ComponentProps<"div">): JSX.Element {
  return <div data-slot="empty-icon" className={cn("mb-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-card bg-accent-tint text-accent", className)} {...props} />;
}

export function EmptyDescription({ className, ...props }: ComponentProps<"p">): JSX.Element {
  return <p data-slot="empty-description" className={cn("text-body leading-relaxed text-ink-secondary", className)} {...props} />;
}

export function EmptyContent({ className, ...props }: ComponentProps<"div">): JSX.Element {
  return <div data-slot="empty-content" className={cn("flex w-full min-w-0 flex-col items-center gap-4 text-body", className)} {...props} />;
}