import type { ReactNode } from "react";

export function MethodologyPopover({ title = "How to read this view", children }: {
  title?: string;
  children: ReactNode;
}): JSX.Element {
  return <details className="disclosure">
    <summary>{title}</summary>
    <div className="space-y-2 p-4 text-body text-ink-secondary">{children}</div>
  </details>;
}