import type { HTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import { SpotlightCard } from "@/components/godui/spotlight-card";

export function Card({ className, children, ...props }: HTMLAttributes<HTMLElement>): JSX.Element {
  return <SpotlightCard as="section" contain={false} wrapContent={false} border={false} className={cn("card min-w-0", className)} {...props}>{children}</SpotlightCard>;
}

export function CardHeader({
  title,
  description,
  action,
  icon: Icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: LucideIcon;
}): JSX.Element {
  return (
    <header className="card-header">
      <div className="workspace-card-heading">
        {Icon ? <span className="workspace-card-icon" aria-hidden="true"><Icon size={16} /></span> : null}
        <div className="min-w-0">
          <h2 className="card-title">{title}</h2>
          {description ? <p className="mt-0.5 text-meta text-ink-secondary">{description}</p> : null}
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

export function CardBody({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}): JSX.Element {
  return <div className={cn("card-body", className)}>{children}</div>;
}
