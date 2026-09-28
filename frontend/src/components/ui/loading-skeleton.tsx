// Skeleton slot/props adapted from shadcn/ui; see ../shadcn/LICENSE.txt and provenance.json.
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/** A neutral placeholder block. Skeletons mirror the shape of the content they replace. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return <div data-slot="skeleton" className={cn("workspace-skeleton rounded bg-surface-subtle", className)} {...props} />;
}

export function SkeletonTable({ rows = 6 }: { rows?: number }): JSX.Element {
  return (
    <div className="divide-y divide-line px-4" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="grid grid-cols-[2fr_1fr_1fr] items-center gap-5 py-4">
          <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-6 w-16 justify-self-end" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 4 }: { count?: number }): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="rounded-card border border-line bg-surface p-5">
          <Skeleton className="h-3 w-2/3" /><Skeleton className="mt-6 h-8 w-1/3" /><Skeleton className="mt-5 h-3 w-4/5" />
        </div>
      ))}
    </div>
  );
}

/** Announce loading for assistive technology while the skeleton handles the visual. */
export function LoadingRegion({ label }: { label: string }): JSX.Element {
  return (
    <span className="sr-only" role="status">
      {label}
    </span>
  );
}
