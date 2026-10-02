import { useState } from "react";
import { History } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { SkeletonTable } from "@/components/ui/loading-skeleton";
import { formatDate, formatDateTime } from "@/lib/format";
import { recordTypeLabel } from "@/lib/terminology";
import { useActivity } from "@/lib/queries";
import type { ActivityFieldChange } from "@/types/api";

// The API returns at most 500 events per request; older history is read in steps up to that.
const FIRST_PAGE = 50;
const STEP = 150;
const MAX_EVENTS = 500;
const SYSTEM_ACTOR = "System";
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** A stored before or after value, as a reader would say it. */
function describeValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && ISO_DATE.test(value)) return formatDate(value);
  if (typeof value === "string" && ISO_DATE_TIME.test(value)) return formatDateTime(value);
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function ChangeList({ changes }: { changes: ActivityFieldChange[] }): JSX.Element {
  return (
    <dl className="mt-1.5 space-y-1 rounded-control border border-line bg-surface-subtle px-3 py-2 text-meta">
      {changes.map(change => (
        <div key={change.field} className="flex flex-wrap gap-x-2">
          <dt className="font-medium text-ink">{change.label}</dt>
          <dd className="text-ink-secondary">
            <span className="line-through decoration-ink-muted/60">{describeValue(change.before)}</span>
            <span aria-hidden="true"> → </span>
            <span className="sr-only"> changed to </span>
            <span className="text-ink">{describeValue(change.after)}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ActivityTab({ projectId }: { projectId: string }): JSX.Element {
  const [limit, setLimit] = useState(FIRST_PAGE);
  const activity = useActivity(projectId, limit);
  const [recordType, setRecordType] = useState("");
  const [person, setPerson] = useState("");
  const [text, setText] = useState("");
  const events = activity.data ?? [];
  const recordTypes = [...new Set(events.map(event => recordTypeLabel(event.entity_type)))].sort();
  const people = [...new Set(events.map(event => event.actor_name ?? SYSTEM_ACTOR))].sort();
  const needle = text.trim().toLowerCase();
  const visible = events.filter(event =>
      (!recordType || recordTypeLabel(event.entity_type) === recordType)
    && (!person || (event.actor_name ?? SYSTEM_ACTOR) === person)
    && (!needle || `${event.headline} ${event.detail ?? ""} ${event.entity_id}`.toLowerCase().includes(needle)));
  const filtered = Boolean(recordType || person || needle);
  const mayHaveMore = events.length >= limit && limit < MAX_EVENTS;

  function clearFilters(): void {
    setRecordType("");
    setPerson("");
    setText("");
  }

  return (
    <Card>
      <CardHeader
        title="Audit trail"
        icon={History}
        description={activity.data
          ? `${mayHaveMore ? `Latest ${events.length}` : `All ${events.length}`} recorded changes, with the person who made them and what changed`
          : "Recorded changes, with the person who made them and what changed"}
      />
      {activity.isLoading ? (
        <SkeletonTable rows={6} />
      ) : activity.isError ? (
        <ErrorState error={activity.error} onRetry={() => void activity.refetch()} />
      ) : events.length === 0 ? (
        <EmptyState
          title="Nothing recorded yet"
          description="Edits made through EPOS are written to this trail as they happen."
        />
      ) : (
        <>
          <div role="group" aria-label="Audit trail filters" className="grid items-end gap-3 border-b border-line px-4 py-3 sm:grid-cols-2 xl:grid-cols-4">
            <Field label="Record type" htmlFor="audit-record-type">
              <Select id="audit-record-type" value={recordType} onChange={event => setRecordType(event.target.value)}>
                <option value="">All record types</option>
                {recordTypes.map(value => <option key={value} value={value}>{value}</option>)}
              </Select>
            </Field>
            <Field label="Changed by" htmlFor="audit-person">
              <Select id="audit-person" value={person} onChange={event => setPerson(event.target.value)}>
                <option value="">Anyone</option>
                {people.map(value => <option key={value} value={value}>{value}</option>)}
              </Select>
            </Field>
            <Field label="Contains" htmlFor="audit-text">
              <TextInput id="audit-text" type="search" value={text} placeholder="A reference or a word from the change"
                onChange={event => setText(event.target.value)} />
            </Field>
            <div className="flex min-h-10 flex-wrap items-center gap-2">
              <span className="text-meta text-ink-secondary" aria-live="polite">
                {filtered ? `${visible.length} of ${events.length} match` : `${events.length} changes`}
              </span>
              {filtered ? <Button size="sm" variant="ghost" onClick={clearFilters}>Clear filters</Button> : null}
            </div>
          </div>
          {visible.length === 0 ? (
            <EmptyState title="No changes match" description="Nothing in the loaded history matches these filters."
              action={<Button onClick={clearFilters}>Clear filters</Button>} className="py-8" />
          ) : (
            <ol className="divide-y divide-line">
              {visible.map((event) => (
                <li key={event.id} className="flex gap-3 px-4 py-3">
                  <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  <div className="min-w-0 flex-1">
                    <p className="text-body text-ink">{event.headline}</p>
                    {event.detail ? <p className="mt-0.5 text-meta text-ink-secondary">{event.detail}</p> : null}
                    {event.changes && event.changes.length > 0 ? <ChangeList changes={event.changes} /> : null}
                    <p className="mt-1 text-meta text-ink-secondary">
                      {recordTypeLabel(event.entity_type)} {event.entity_id} ·{" "}
                      {event.actor_name ?? SYSTEM_ACTOR} ·{" "}
                      {formatDateTime(event.occurred_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
          {mayHaveMore ? (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3">
              <p className="text-meta text-ink-secondary">Filters search the loaded history. Load older changes to search further back.</p>
              <Button size="sm" disabled={activity.isFetching} onClick={() => setLimit(current => Math.min(MAX_EVENTS, current + STEP))}>
                {activity.isFetching ? "Loading" : "Load older changes"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}
