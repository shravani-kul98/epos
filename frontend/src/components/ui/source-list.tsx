import { useState } from "react";

import { cn } from "@/lib/cn";
import { EvidenceDrawer } from "@/components/ui/evidence-drawer";

const PREVIEW_COUNT = 6;

interface SourceListProps {
  ids: string[];
  label?: string;
  className?: string;
}

/**
 * Renders the record identifiers behind a conclusion. Every calculated statement in EPOS is
 * expected to cite its evidence, so this component appears wherever a figure is presented.
 */
export function SourceList({ ids, label = "Sources", className }: SourceListProps): JSX.Element | null {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  if (ids.length === 0) return null;

  const uniqueIds = [...new Set(ids)];
  const visible = expanded ? uniqueIds : uniqueIds.slice(0, PREVIEW_COUNT);
  const remaining = uniqueIds.length - visible.length;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <span className="text-meta text-ink-secondary">{label}:</span>
      {visible.map((id) => (
        <button
          key={id}
          type="button"
          aria-label={`Inspect source ${id}`}
          onClick={() => setSelected(id)}
          className="min-h-8 rounded-control border border-line bg-surface-subtle px-2 py-1 text-identifier text-accent hover:border-accent"
        >
          <code>{id}</code>
        </button>
      ))}
      {remaining > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="min-h-8 text-meta font-medium text-accent hover:underline"
        >
          show {remaining} more
        </button>
      ) : null}
      {selected ? <EvidenceDrawer reference={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
