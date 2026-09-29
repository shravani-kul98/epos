import { useEffect, useId, useRef, useState } from "react";
import { ArrowRightLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Field, TextArea } from "@/components/ui/form";
import { ApiError } from "@/lib/api";

export interface LifecycleMove {
  target: string;
  label: string;
  /** Statuses the move is offered from. This mirrors the API's rules; the API still decides. */
  from: readonly string[];
  reasonLabel?: string;
  reasonHint?: string;
  /** Starting work needs no justification; every other step records one. */
  reasonOptional?: boolean;
  danger?: boolean;
}

/** True when a write was refused because the record changed after it was loaded. */
export function isStaleVersion(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.message.startsWith("This record changed after it was loaded");
}

/** A refusal from the API. Reopening advice is given only when the record really changed. */
export function MutationError({ error, stale }: {
  error: Error | null;
  stale?: string;
}): JSX.Element | null {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical">
      <p>{error.message}</p>
      {stale && isStaleVersion(error) ? <p className="mt-1">{stale}</p> : null}
    </div>
  );
}

// The record whose step was just confirmed. Its section remounts with the new status and takes
// focus back, so keyboard users are not dropped to the top of the page.
let confirmedRecord: string | null = null;

/**
 * The next lifecycle steps a record can take, each confirmed with its reason. It sits inside the
 * record's own panel, so the reader keeps the context they are deciding on.
 */
export function LifecycleSection({ title = "Next step", status, moves, onConfirm, pending, disabled = false, recordLabel, notice }: {
  title?: string;
  status: string;
  moves: readonly LifecycleMove[];
  onConfirm: (move: LifecycleMove, reason: string) => Promise<unknown>;
  pending: boolean;
  disabled?: boolean;
  recordLabel: string;
  /** Why an expected step is not offered right now, for example an unmet mandatory criterion. */
  notice?: string;
}): JSX.Element | null {
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const [chosen, setChosen] = useState<LifecycleMove | null>(null);
  const [reason, setReason] = useState("");
  const [failure, setFailure] = useState<Error | null>(null);
  useEffect(() => {
    if (confirmedRecord === recordLabel) {
      confirmedRecord = null;
      heading.current?.focus();
    }
  }, [recordLabel]);
  const available = moves.filter(move => move.from.includes(status));
  if (available.length === 0 && !notice) return null;
  const trimmed = reason.trim();
  const reasonNeeded = !chosen?.reasonOptional;

  function choose(move: LifecycleMove | null): void {
    setChosen(move);
    setReason("");
    setFailure(null);
  }

  async function confirm(): Promise<void> {
    if (!chosen || (reasonNeeded && !trimmed)) return;
    setFailure(null);
    try {
      confirmedRecord = recordLabel;
      await onConfirm(chosen, trimmed);
      choose(null);
    } catch (caught) {
      confirmedRecord = null;
      // The refusal is shown below and the reason is kept for correction.
      setFailure(caught instanceof Error ? caught : new Error("The change could not be saved."));
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="space-y-3 rounded-card border border-line bg-surface-subtle p-4">
      <div className="flex items-start gap-2">
        <ArrowRightLeft aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <div>
          <h3 id={`${id}-title`} ref={heading} tabIndex={-1} className="text-card font-medium text-ink focus:outline-none">{title}</h3>
          <p className="mt-0.5 text-meta text-ink-secondary">Currently {status}. Each step is kept in the audit trail.</p>
        </div>
      </div>
      <div role="group" aria-label={`Next steps for ${recordLabel}`} className="flex flex-wrap gap-2">
        {available.map(move => {
          const active = chosen?.target === move.target && chosen.label === move.label;
          return (
            <Button key={`${move.target}-${move.label}`} size="sm" variant={active ? "primary" : "secondary"} aria-pressed={active}
              disabled={disabled || pending} onClick={() => choose(active ? null : move)}>
              {move.label}
            </Button>
          );
        })}
      </div>
      {notice ? <p className="text-meta text-ink-secondary">{notice}</p> : null}
      {chosen ? (
        <form className="space-y-3" onSubmit={event => { event.preventDefault(); void confirm(); }}>
          <Field label={chosen.reasonLabel ?? "Reason"} htmlFor={`${id}-reason`}
            hint={chosen.reasonHint ?? (reasonNeeded ? "Required. Kept with the change in the audit trail." : "Optional. Kept with the change in the audit trail.")}>
            <TextArea id={`${id}-reason`} rows={3} maxLength={2000} required={reasonNeeded} value={reason} onChange={event => setReason(event.target.value)} />
          </Field>
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" disabled={pending} onClick={() => choose(null)}>Cancel</Button>
            <Button size="sm" type="submit" variant={chosen.danger ? "danger" : "primary"} disabled={pending || (reasonNeeded && !trimmed)}>
              {pending ? "Saving" : `Confirm ${chosen.label.toLowerCase()}`}
            </Button>
          </div>
        </form>
      ) : null}
      <MutationError error={failure} stale="Close this panel and reopen the record to review the latest version." />
    </section>
  );
}
