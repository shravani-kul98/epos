import { formatDateTime } from "@/lib/format";
import { useTaskProgress } from "@/lib/queries";
import type { ActivityFieldChange } from "@/types/api";

const ACTION_LABELS: Record<string, string> = {
  created: "Created",
  updated: "Updated",
  completed: "Completed",
  reopened: "Reopened",
  review_accepted: "Accepted by reviewer",
  review_returned: "Returned for rework",
};

// These labels already name the reviewer's part, so the person follows a separator rather than "by".
const REVIEW_ACTIONS = new Set(["review_accepted", "review_returned"]);

function shown(change: ActivityFieldChange, value: unknown): string {
  if (value === null || value === undefined || value === "") return "none";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return change.field === "completion_percent" ? `${String(value)}%` : String(value);
}

function describe(change: ActivityFieldChange): string {
  return `${change.label}: ${shown(change, change.before)} → ${shown(change, change.after)}`;
}

/** The task's reports, newest first, so progress can be read in the assignee's own words. */
export function TaskProgressHistory({ taskId }: { taskId: string }): JSX.Element {
  const history = useTaskProgress(taskId);
  const entries = history.data ?? [];
  const headingId = `task-history-${taskId}`;

  return (
    <section aria-labelledby={headingId} className="mt-5 border-t border-line pt-4">
      <h3 id={headingId} className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
        Progress history
      </h3>
      {history.isLoading ? (
        <p className="mt-2 text-meta text-ink-secondary">Loading progress history…</p>
      ) : history.isError ? (
        <p role="alert" className="mt-2 text-meta text-critical">{history.error.message}</p>
      ) : entries.length === 0 ? (
        <p className="mt-2 text-meta text-ink-secondary">No progress has been reported yet.</p>
      ) : (
        <ol className="mt-2 space-y-2">
          {entries.map((entry, index) => {
            const changes = entry.changes ?? [];
            return (
              <li key={`${entry.id}-${index}`} className="rounded-control border border-line px-3 py-2">
                <p className="text-meta text-ink-muted">
                  {ACTION_LABELS[entry.action] ?? "Updated"}{REVIEW_ACTIONS.has(entry.action) ? " · " : " by "}{entry.actor_name ?? "an unrecorded person"} ·{" "}
                  {formatDateTime(entry.occurred_at)}
                </p>
                {changes.length > 0 ? (
                  <p className="mt-1 text-meta text-ink-secondary">{changes.map(describe).join(" · ")}</p>
                ) : null}
                {entry.note ? <p className="mt-1 whitespace-pre-wrap text-body text-ink">{entry.note}</p> : null}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
