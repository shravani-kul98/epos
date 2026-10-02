import { useState } from "react";
import { History, Minus, Pencil, Plus } from "lucide-react";

import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Section } from "@/components/ui/section";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useProjectDelta } from "@/lib/queries";
import type { ProjectDeltaEntry } from "@/types/api";

const WINDOWS = [
  { days: 7, label: "7 days" },
  { days: 14, label: "14 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
] as const;

const CHANGE_STYLE: Record<
  ProjectDeltaEntry["change_type"],
  { icon: typeof Plus; label: string; className: string }
> = {
  added: { icon: Plus, label: "Added", className: "bg-ok-tint text-ok" },
  updated: { icon: Pencil, label: "Updated", className: "bg-accent-tint text-accent" },
  withdrawn: { icon: Minus, label: "Withdrawn", className: "bg-critical-tint text-critical" },
};

function ChangeRow({ entry }: { entry: ProjectDeltaEntry }): JSX.Element {
  const style = CHANGE_STYLE[entry.change_type];
  const Icon = style.icon;

  return (
    <li className="flex gap-3 px-4 py-2.5">
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
          style.className,
        )}
      >
        <Icon className="h-3 w-3" />
      </span>
      <div className="min-w-0">
        <p className="text-body text-ink">{entry.headline}</p>
        <p className="mt-0.5 text-meta text-ink-muted">
          <span className="sr-only">{style.label}. </span>
          {entry.entity_id}
          {entry.actor_name ? ` · ${entry.actor_name}` : ""} · {formatDateTime(entry.occurred_at)}
        </p>
      </div>
    </li>
  );
}

function countLine(added: number, updated: number, withdrawn: number): string {
  const parts: string[] = [];
  if (added) parts.push(`${added} added`);
  if (updated) parts.push(`${updated} updated`);
  if (withdrawn) parts.push(`${withdrawn} withdrawn`);
  return parts.join(" · ");
}

/**
 * Answers "what changed since last review?" from the audit trail the records already carry. The
 * window is chosen by the reader because a review cadence is a human decision, not a stored one.
 */
export function WhatChanged({ projectId }: { projectId: string }): JSX.Element {
  const [days, setDays] = useState<number>(7);
  const delta = useProjectDelta(projectId, days);

  const selector = (
    <div className="flex items-center gap-1 rounded-control border border-line bg-surface p-0.5">
      {WINDOWS.map((window) => (
        <button
          key={window.days}
          type="button"
          onClick={() => setDays(window.days)}
          aria-pressed={days === window.days}
          className={cn(
            "rounded px-2.5 py-1 text-meta font-medium",
            days === window.days
              ? "bg-accent-tint text-accent"
              : "text-ink-secondary hover:text-ink",
          )}
        >
          {window.label}
        </button>
      ))}
    </div>
  );

  return (
    <Section
      title="What changed"
      description={`Movement across the project in the last ${days} days`}
      icon={History}
      accent="cyan"
      actions={selector}
    >
      {delta.isError ? (
        <Card>
          <ErrorState error={delta.error} onRetry={() => void delta.refetch()} />
        </Card>
      ) : delta.isLoading ? (
        <Card>
          <CardBody>
            <p className="text-body text-ink-secondary">Reading the project history…</p>
          </CardBody>
        </Card>
      ) : !delta.data?.has_history ? (
        <Card>
          <EmptyState
            title="No earlier project snapshot is available yet"
            description="This project holds no record older than the selected window, so there is nothing to compare it against. Come back after the next reporting cycle."
            className="py-8"
          />
        </Card>
      ) : delta.data.total_changes === 0 ? (
        <Card>
          <EmptyState
            title="Nothing changed in this window"
            description={`No record on this project was added, updated or withdrawn in the last ${days} days.`}
            className="py-8"
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {delta.data.groups.map((group) => (
            <Card key={group.key}>
              <CardHeader
                title={group.label}
                description={countLine(group.added, group.updated, group.withdrawn)}
              />
              <ul className="divide-y divide-line">
                {group.entries.map((entry) => (
                  <ChangeRow key={`${entry.entity_type}-${entry.entity_id}`} entry={entry} />
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </Section>
  );
}
