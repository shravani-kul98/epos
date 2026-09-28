import type { ReactNode } from "react";
import { FolderOpen } from "lucide-react";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/shadcn/empty";

import { cn } from "@/lib/cn";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
  /** Set to 2 when the empty state is the first content under the page title, so levels don't skip. */
  headingLevel?: 2 | 3;
}

/** Empty is not an error. Say what would appear here and how to make it appear. */
export function EmptyState({
  title,
  description,
  action,
  className,
  headingLevel = 3,
}: EmptyStateProps): JSX.Element {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <Empty className={cn("py-12", className)}>
      <EmptyHeader><EmptyMedia aria-hidden="true"><FolderOpen size={23} strokeWidth={1.5} /></EmptyMedia>
        <Heading className="text-section font-semibold text-ink">{title}</Heading>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  );
}
