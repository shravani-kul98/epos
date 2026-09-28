import { createContext, useContext, type ReactNode } from "react";
import { CalendarDays, Layers3 } from "lucide-react";

import { TermHelp } from "@/components/ui/term-help";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

export const PageContext = createContext<{ scope?: string; asOfDate?: string }>({});

interface PageHeaderProps {
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
  scope?: string;
  asOfDate?: string;
}

export function PageHeader({
  title,
  description,
  meta,
  actions,
  className,
  scope,
  asOfDate,
}: PageHeaderProps): JSX.Element {
  const context = useContext(PageContext);
  const scopeLabel = scope ?? context.scope;
  const analysisDate = asOfDate ?? context.asOfDate;
  return (
    <header className={cn("workspace-page-header mb-6 flex flex-wrap items-start justify-between gap-4", className)}>
      <div className="min-w-0 flex-1 basis-64">
        {scopeLabel || analysisDate ? <div className="workspace-page-context">
          {scopeLabel ? <span><Layers3 size={13} aria-hidden="true" />{scopeLabel}</span> : null}
          {analysisDate ? <span><CalendarDays size={13} aria-hidden="true" />Analysis date <time dateTime={analysisDate}>{formatDate(analysisDate)}</time></span> : null}
          {analysisDate ? <TermHelp term="analysisDate" /> : null}
        </div> : null}
        <h1 className="break-words text-title font-semibold leading-tight text-ink">{title}</h1>
        {description ? <p className="workspace-page-description mt-1.5 text-body text-ink-secondary">{description}</p> : null}
        {meta ? <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div> : null}
      </div>
      {actions ? <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
