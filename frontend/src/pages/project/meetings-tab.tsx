import { useState } from "react";
import { CircleAlert, Gavel, ListChecks, Plus } from "lucide-react";

import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { RECORD_OWNER_PERMISSIONS, useProjectPeople } from "@/lib/people-queries";
import {
  useCaptureMeetingNote,
  useMeetingNoteExtraction,
  useMeetingNotes,
  usePromoteProposal,
} from "@/lib/queries";
import type { MeetingNote, MeetingNoteProposal, ProjectUserOption } from "@/types/api";

const KIND_STYLE: Record<
  MeetingNoteProposal["kind"] | "issue",
  { label: string; article: string; icon: typeof ListChecks; className: string }
> = {
  action: { label: "Action", article: "an", icon: ListChecks, className: "bg-accent-tint text-accent" },
  risk: { label: "Risk", article: "a", icon: CircleAlert, className: "bg-warn-tint text-warn" },
  issue: { label: "Issue", article: "an", icon: CircleAlert, className: "bg-critical-tint text-critical" },
  decision: { label: "Decision", article: "a", icon: Gavel, className: "bg-purple-tint text-purple" },
};

interface ReviewState {
  proposal: MeetingNoteProposal;
  text: string;
  owner: string;
  ownerId: number | null;
  ownerConfirmed: boolean;
  dueDate: string;
  // A risk is scored by the reviewer; extraction never guesses probability or impact.
  probability: string;
  impact: string;
}

const LEVELS = [1, 2, 3, 4, 5];

function plural(count: number, noun: string): string {
  return `${count} ${count === 1 ? noun : `${noun}s`}`;
}

/** The one member a name written in the note refers to, by full name or first name, if any. */
function matchingMember(name: string | null, people: ProjectUserOption[]): ProjectUserOption | undefined {
  const wanted = name?.trim().toLowerCase();
  if (!wanted) return undefined;
  const exact = people.filter(person => person.full_name.toLowerCase() === wanted);
  if (exact.length === 1) return exact[0];
  const first = people.filter(person => person.full_name.toLowerCase().split(/\s+/)[0] === wanted);
  return first.length === 1 ? first[0] : undefined;
}

function ProposalRow({
  proposal,
  onAccept,
  dismissed,
  onDismiss,
  canPromote,
}: {
  proposal: MeetingNoteProposal;
  onAccept: () => void;
  dismissed: boolean;
  onDismiss: () => void;
  canPromote: boolean;
}): JSX.Element {
  const style = KIND_STYLE[proposal.kind];
  const Icon = style.icon;

  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${style.className}`}
        >
          <Icon className="h-3 w-3" />
        </span>
        <div className="min-w-0 flex-1">
          <p className={dismissed ? "text-body text-ink-muted line-through" : "text-body text-ink"}>
            {proposal.text}
          </p>
          <p className="mt-0.5 text-meta text-ink-muted">
            {style.label} · line {proposal.source_line_number} · matched &ldquo;
            {proposal.matched_phrase}&rdquo;
            {proposal.suggested_owner ? ` · ${proposal.suggested_owner}` : ""}
          </p>
        </div>
        {dismissed ? (
          <Button size="sm" onClick={onDismiss}>
            Restore
          </Button>
        ) : (
          <div className="flex shrink-0 gap-1.5">
            <Button size="sm" onClick={onDismiss}>
              Dismiss
            </Button>
            {canPromote ? (
              <Button size="sm" variant="primary" onClick={onAccept}>
                Accept
              </Button>
            ) : null}
          </div>
        )}
      </div>
    </li>
  );
}

/**
 * Meeting notes and the follow-ups EPOS reads out of them. Extraction is pattern matching over the
 * note, not generation, so every proposal shows the line and the phrase it came from. Nothing
 * becomes a project record until someone accepts it and confirms the wording.
 */
export function MeetingsTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const notes = useMeetingNotes(projectId);
  const capture = useCaptureMeetingNote(projectId);
  const promote = usePromoteProposal();

  const [openNote, setOpenNote] = useState<MeetingNote | null>(null);
  const extraction = useMeetingNoteExtraction(openNote?.note_id ?? null);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [review, setReview] = useState<ReviewState | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [ownerError, setOwnerError] = useState<string | undefined>();
  const [created, setCreated] = useState<string | null>(null);
  const people = useProjectPeople(review ? projectId : "", review?.proposal.kind ?? "action");
  const suggestion = review ? matchingMember(review.proposal.suggested_owner, people.data ?? []) : undefined;

  const [capturing, setCapturing] = useState(false);
  const [draft, setDraft] = useState({
    title: "",
    meetingDate: new Date().toISOString().slice(0, 10),
    attendees: "",
    body: "",
  });
  const [captureError, setCaptureError] = useState<string | null>(null);

  const canCapture = can("work.update");

  function openProposal(proposal: MeetingNoteProposal): void {
    // A name read from the note is only a suggestion; the reviewer chooses the member.
    setReview({
      proposal,
      text: proposal.text,
      owner: "",
      ownerId: null,
      ownerConfirmed: false,
      dueDate: proposal.suggested_due_date ?? "",
      probability: "",
      impact: "",
    });
    setReviewError(null);
    setOwnerError(undefined);
  }

  function toggleDismissed(id: string): void {
    setDismissed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function confirmPromotion(): Promise<void> {
    if (!review || !openNote) return;
    setReviewError(null);
    setOwnerError(undefined);
    if (review.text.trim().length < 5 || !review.owner.trim() || !review.ownerConfirmed) {
      if (!review.owner.trim() || !review.ownerConfirmed) setOwnerError("Choose a registered project member; extracted names are not confirmed assignments.");
      setReviewError("Confirm the wording and choose a registered project member before this becomes a record.");
      return;
    }
    const isRisk = review.proposal.kind === "risk";
    if (isRisk && (!review.probability || !review.impact)) {
      setReviewError("Choose the probability and impact you assess for this risk.");
      return;
    }
    try {
      const record = await promote.mutateAsync({
        noteId: openNote.note_id,
        kind: review.proposal.kind,
        text: review.text.trim(),
        owner: review.owner.trim(),
        // Actions and risks are linked to the owner's account, so they are told and see the work.
        ...(review.proposal.kind !== "decision" && review.ownerId ? { owner_user_id: review.ownerId } : {}),
        ...(review.dueDate ? { due_date: review.dueDate } : {}),
        ...(isRisk ? { probability: Number(review.probability), impact: Number(review.impact) } : {}),
        source_line_number: review.proposal.source_line_number,
      });
      const createdId = [record.action_id, record.risk_id, record.decision_id].find((value): value is string => typeof value === "string");
      const kindLabel = KIND_STYLE[review.proposal.kind].label.toLowerCase();
      setCreated(createdId
        ? `Created ${kindLabel} ${createdId} for ${review.owner.trim()}.`
        : `Created the ${kindLabel} for ${review.owner.trim()}.`);
      setDismissed((current) => new Set(current).add(review.proposal.proposal_id));
      setReview(null);
    } catch (caught) {
      if (caught instanceof ApiError) setOwnerError(caught.fieldErrors.owner);
      setReviewError(caught instanceof ApiError ? caught.message : "The record could not be created.");
    }
  }

  async function submitNote(): Promise<void> {
    setCaptureError(null);
    if (draft.title.trim().length < 3 || draft.body.trim().length < 10) {
      setCaptureError("Give the meeting a title and paste the notes.");
      return;
    }
    try {
      await capture.mutateAsync({
        project_id: projectId,
        title: draft.title.trim(),
        meeting_date: draft.meetingDate,
        attendees: draft.attendees.trim() || null,
        body: draft.body,
      });
      setCapturing(false);
      setDraft({
        title: "",
        meetingDate: new Date().toISOString().slice(0, 10),
        attendees: "",
        body: "",
      });
    } catch (caught) {
      setCaptureError(caught instanceof ApiError ? caught.message : "The note could not be saved.");
    }
  }

  const columns: Column<MeetingNote>[] = [
    {
      key: "title",
      header: "Meeting",
      value: (row) => row.title,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-medium text-ink">{row.title}</p>
          <p className="text-meta text-ink-muted">{row.note_id}</p>
        </div>
      ),
    },
    {
      key: "attendees",
      header: "Attendees",
      value: (row) => row.attendees ?? "",
      cell: (row) => <span className="text-ink-secondary">{row.attendees ?? "Not recorded"}</span>,
    },
    {
      key: "date",
      header: "Held",
      align: "right",
      value: (row) => row.meeting_date,
      cell: (row) => formatDate(row.meeting_date),
    },
  ];

  const remaining = (extraction.data?.proposals ?? []).filter(
    (item) => !dismissed.has(item.proposal_id),
  );

  return (
    <>
      <DataTable
        rows={notes.data}
        columns={columns}
        rowKey={(row) => row.note_id}
        isLoading={notes.isLoading}
        error={notes.isError ? notes.error : undefined}
        onRetry={() => void notes.refetch()}
        onRowClick={(row) => {
          setOpenNote(row);
          setDismissed(new Set());
          setCreated(null);
        }}
        searchPlaceholder="Filter meetings"
        emptyTitle="No meeting notes"
        emptyDescription="Paste the notes from a delivery meeting and EPOS will point out the actions, risks and decisions inside them."
        emptyAction={
          canCapture ? (
            <Button variant="primary" onClick={() => setCapturing(true)}>
              Capture a note
            </Button>
          ) : undefined
        }
        toolbar={
          canCapture ? (
            <Button size="sm" variant="primary" onClick={() => setCapturing(true)}>
              <Plus aria-hidden="true" className="h-3.5 w-3.5" />
              Capture note
            </Button>
          ) : undefined
        }
      />

      <Drawer
        open={openNote !== null}
        onClose={() => setOpenNote(null)}
        title={openNote?.title ?? "Meeting note"}
        description={
          openNote
            ? `${openNote.note_id} · ${formatDate(openNote.meeting_date)}${openNote.attendees ? ` · ${openNote.attendees}` : ""}`
            : undefined
        }
        width="max-w-3xl"
        footer={<Button onClick={() => setOpenNote(null)}>Close</Button>}
      >
        {openNote ? (
          <div className="space-y-5">
            {created ? <p role="status" className="rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{created}</p> : null}
            <Card>
              <CardHeader
                title="Follow-ups found in this note"
                description={
                  extraction.data
                    ? `${plural(extraction.data.action_count, "action")}, ${plural(extraction.data.risk_count, "risk")} and ${plural(extraction.data.decision_count, "decision")} were read from the words in this note. Nothing exists as a record until you accept it.`
                    : "Read from the words in the note. Nothing here exists as a record until you accept it."
                }
              />
              {extraction.isLoading ? (
                <CardBody>
                  <p className="text-body text-ink-secondary">Reading the note…</p>
                </CardBody>
              ) : remaining.length === 0 ? (
                <EmptyState
                  title={
                    (extraction.data?.proposals.length ?? 0) > 0
                      ? "Everything here has been handled"
                      : "Nothing to follow up"
                  }
                  description={
                    (extraction.data?.proposals.length ?? 0) > 0
                      ? "Every proposal from this note has been accepted or dismissed."
                      : "No line in this note names an action, a risk or a decision."
                  }
                  className="py-8"
                />
              ) : (
                <ul className="divide-y divide-line">
                  {remaining.map((proposal) => (
                    <ProposalRow
                      key={proposal.proposal_id}
                      proposal={proposal}
                      canPromote={can(RECORD_OWNER_PERMISSIONS[proposal.kind])}
                      dismissed={false}
                      onDismiss={() => toggleDismissed(proposal.proposal_id)}
                      onAccept={() => openProposal(proposal)}
                    />
                  ))}
                </ul>
              )}
            </Card>

            <section>
              <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
                The note as written
              </h3>
              <pre className="mt-2 whitespace-pre-wrap rounded-card border border-line bg-surface-subtle px-3 py-2.5 font-sans text-body text-ink">
                {openNote.body}
              </pre>
            </section>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={review !== null}
        busy={promote.isPending}
        dirty={review!==null&&(review.ownerConfirmed||review.text!==review.proposal.text||review.dueDate!==(review.proposal.suggested_due_date??"")||review.probability!==""||review.impact!=="")}
        onClose={() => setReview(null)}
        title={review ? `Create ${KIND_STYLE[review.proposal.kind].article} ${KIND_STYLE[review.proposal.kind].label.toLowerCase()}` : "Confirm"}
        description="The record is created with the wording you confirm here, not the wording EPOS read."
        footer={(close) =>
          <>
            <Button onClick={close}>Cancel</Button>
            <Button variant="primary" onClick={() => void confirmPromotion()} disabled={promote.isPending}>
              {promote.isPending ? "Creating" : "Create record"}
            </Button>
          </>
        }
      >
        {review ? (
          <div className="space-y-4">
            <p className="rounded-control border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
              From line {review.proposal.source_line_number}: {review.proposal.source_line}
            </p>
            <Field label="Wording" htmlFor="proposal-text">
              <TextArea
                id="proposal-text"
                rows={3}
                value={review.text}
                onChange={(event) => setReview({ ...review, text: event.target.value })}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <RecordOwnerField
                    key={review.proposal.proposal_id}
                    projectId={projectId}
                    purpose={review.proposal.kind}
                    label="Owner"
                    id="proposal-owner"
                    required
                    value={review.owner || null}
                    userId={review.ownerId}
                    linksAccount={review.proposal.kind !== "decision"}
                    error={ownerError}
                    onChange={(name, userId) => { setReview({ ...review, owner: name ?? "", ownerId: userId, ownerConfirmed: Boolean(name) }); setOwnerError(undefined); }}
                  />
                {!review.owner && review.proposal.suggested_owner ? (
                  suggestion ? (
                    <p className="flex flex-wrap items-center gap-2 text-meta text-ink-secondary">
                      The note names “{review.proposal.suggested_owner}”.
                      <Button size="sm" onClick={() => { setReview({ ...review, owner: suggestion.full_name, ownerId: suggestion.user_id, ownerConfirmed: true }); setOwnerError(undefined); }}>
                        Use {suggestion.full_name}
                      </Button>
                    </p>
                  ) : (
                    <p className="text-meta text-ink-secondary">The note names “{review.proposal.suggested_owner}”, who is not a single project member. Choose the owner.</p>
                  )
                ) : null}
              </div>
              {review.proposal.kind === "decision" ? null : (
                <Field
                  label="Due"
                  htmlFor="proposal-due"
                  hint="Leave blank to use two weeks from today."
                >
                  <TextInput
                    id="proposal-due"
                    type="date"
                    value={review.dueDate}
                    onChange={(event) => setReview({ ...review, dueDate: event.target.value })}
                  />
                </Field>
              )}
            </div>
            {review.proposal.kind === "risk" ? (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Probability" htmlFor="proposal-probability" hint="1 is unlikely, 5 is near certain.">
                  <Select
                    id="proposal-probability"
                    required
                    value={review.probability}
                    onChange={(event) => setReview({ ...review, probability: event.target.value })}
                  >
                    <option value="">Choose</option>
                    {LEVELS.map((level) => <option key={level} value={level}>{level}</option>)}
                  </Select>
                </Field>
                <Field label="Impact" htmlFor="proposal-impact" hint="1 is minor, 5 is severe.">
                  <Select
                    id="proposal-impact"
                    required
                    value={review.impact}
                    onChange={(event) => setReview({ ...review, impact: event.target.value })}
                  >
                    <option value="">Choose</option>
                    {LEVELS.map((level) => <option key={level} value={level}>{level}</option>)}
                  </Select>
                </Field>
              </div>
            ) : null}
            {reviewError ? (
              <p
                className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical"
                role="alert"
              >
                {reviewError}
              </p>
            ) : null}
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={capturing}
        dirty={Boolean(draft.title||draft.body||draft.attendees)}
        busy={capture.isPending}
        onClose={() => setCapturing(false)}
        title="Capture a meeting note"
        description="Paste the notes as they were written. EPOS will read the follow-ups out of them."
        width="max-w-2xl"
        footer={(close) =>
          <>
            <Button onClick={close}>Cancel</Button>
            <Button variant="primary" onClick={() => void submitNote()} disabled={capture.isPending}>
              {capture.isPending ? "Saving" : "Save note"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Meeting" htmlFor="note-title">
            <TextInput
              id="note-title"
              value={draft.title}
              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              placeholder="Weekly delivery review"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Held on" htmlFor="note-date">
              <TextInput
                id="note-date"
                type="date"
                value={draft.meetingDate}
                onChange={(event) => setDraft({ ...draft, meetingDate: event.target.value })}
              />
            </Field>
            <Field label="Attendees" htmlFor="note-attendees" hint="Optional.">
              <TextInput
                id="note-attendees"
                value={draft.attendees}
                onChange={(event) => setDraft({ ...draft, attendees: event.target.value })}
              />
            </Field>
          </div>
          <Field
            label="Notes"
            htmlFor="note-body"
            hint="One point per line reads best. Lines naming an owner or a date are picked up."
          >
            <TextArea
              id="note-body"
              rows={10}
              value={draft.body}
              onChange={(event) => setDraft({ ...draft, body: event.target.value })}
              placeholder={"Alex to confirm supplier capacity by 2026-09-04.\nWe agreed to hold the pilot until qualification completes.\nRisk: the second source might slip."}
            />
          </Field>
          {captureError ? (
            <p
              className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical"
              role="alert"
            >
              {captureError}
            </p>
          ) : null}
        </div>
      </Drawer>
    </>
  );
}
