import { Link } from "react-router-dom";

import { TaskReviewActions } from "@/components/tasks/task-review-actions";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingRegion, SkeletonTable } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { StatusBadge, type Tone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDate, formatDateTime } from "@/lib/format";
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications, useReviewQueue } from "@/lib/queries";
import type { InboxNotification, Task } from "@/types/api";

const KIND_LABELS: Record<string, string> = {
  task_assigned: "Task assigned",
  task_blocked: "Task blocked",
  task_completed: "Task completed",
  review_requested: "Review requested",
  review_accepted: "Work accepted",
  review_returned: "Returned for rework",
  action_assigned: "Action assigned",
  risk_assigned: "Risk mitigation assigned",
  issue_assigned: "Issue assigned",
  assumption_assigned: "Assumption assigned",
  assignment_accepted: "Assignment accepted",
  assignment_declined: "Assignment declined",
};

const KIND_TONES: Record<string, Tone> = {
  task_blocked: "critical",
  task_completed: "ok",
  review_requested: "accent",
  review_accepted: "ok",
  review_returned: "warn",
  assignment_accepted: "ok",
  assignment_declined: "warn",
};

const REGISTER_TABS: Record<string, string> = {
  Action: "team",
  Risk: "risks",
  Issue: "issues",
  Assumption: "assumptions",
};

/** Where a notification's record can be opened, or null when it names no project. */
function recordPath(notification: InboxNotification): string | null {
  if (!notification.project_id) return null;
  if (notification.entity_type === "Task" && notification.entity_id) {
    return `/projects/${notification.project_id}?tab=work&task=${encodeURIComponent(notification.entity_id)}`;
  }
  const tab = notification.entity_type ? REGISTER_TABS[notification.entity_type] : undefined;
  if (tab) return `/projects/${notification.project_id}?tab=${tab}`;
  return `/projects/${notification.project_id}`;
}

function NotificationItem({ notification, onOpen, onMarkRead, busy }: {
  notification: InboxNotification;
  onOpen: (notification: InboxNotification) => void;
  onMarkRead: (notification: InboxNotification) => void;
  busy: boolean;
}): JSX.Element {
  const unread = notification.read_at === null;
  const path = recordPath(notification);
  const titleClass = cn("mt-1 block text-body", unread ? "font-semibold text-ink" : "text-ink-secondary");
  const context = [notification.actor_name ? `From ${notification.actor_name}` : null, notification.project_id].filter(Boolean).join(" · ");

  return <li className={cn("flex items-start gap-3 border-l-2 px-4 py-3", unread ? "border-accent" : "border-transparent")}>
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={KIND_LABELS[notification.kind] ?? "Update"} tone={KIND_TONES[notification.kind] ?? "neutral"} />
        {unread ? <span className="text-meta font-semibold text-accent">Unread</span> : null}
        <time dateTime={notification.created_at} className="text-meta text-ink-muted">{formatDateTime(notification.created_at)}</time>
      </div>
      {path ? <Link to={path} onClick={() => onOpen(notification)} className={cn(titleClass, "hover:text-accent hover:underline")}>{notification.title}</Link>
        : <p className={titleClass}>{notification.title}</p>}
      {notification.detail ? <p className="mt-1 whitespace-pre-wrap text-meta text-ink-secondary">{notification.detail}</p> : null}
      {context ? <p className="mt-1 text-meta text-ink-muted">{context}</p> : null}
    </div>
    {unread && !path ? <Button size="sm" disabled={busy} onClick={() => onMarkRead(notification)}>Mark as read</Button> : null}
  </li>;
}

function ReviewQueue(): JSX.Element {
  const queue = useReviewQueue();
  const columns: Column<Task>[] = [
    {
      key: "task",
      header: "Task",
      value: (row) => `${row.task_name} ${row.task_id} ${row.project_id}`,
      cell: (row) => (
        <div className="min-w-0">
          <Link to={`/projects/${row.project_id}?tab=work&task=${encodeURIComponent(row.task_id)}`} className="font-medium text-ink hover:text-accent">
            {row.task_name}
          </Link>
          <p className="text-meta text-ink-muted">{row.task_id} · {row.project_id}</p>
        </div>
      ),
    },
    { key: "owner", header: "Assigned to", value: (row) => row.owner ?? "", cell: (row) => row.owner ?? "Unassigned" },
    { key: "reported", header: "Reported", align: "right", value: (row) => row.last_updated_date ?? "", cell: (row) => formatDate(row.last_updated_date) },
    { key: "review", header: "Review", cell: (row) => <div className="flex flex-wrap gap-2"><TaskReviewActions task={row} /></div> },
  ];

  return <Section title="Awaiting your review" description="Completed work waiting for you to accept it or return it for rework.">
    <DataTable
      rows={queue.data}
      label="Awaiting your review"
      columns={columns}
      rowKey={(row) => row.task_id}
      isLoading={queue.isLoading}
      error={queue.isError ? queue.error : undefined}
      onRetry={() => void queue.refetch()}
      searchPlaceholder="Filter tasks awaiting review"
      initialSortKey="reported"
      emptyTitle="Nothing awaiting review"
      emptyDescription="Tasks that need a manager's acceptance appear here once their assignee completes them."
    />
  </Section>;
}

/** The signed-in user's notifications, with the review queue for people who manage work. */
export function InboxPage(): JSX.Element {
  const { can } = useAuth();
  const notifications = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();
  const rows = notifications.data ?? [];
  const unread = rows.filter(row => row.read_at === null).length;

  function open(notification: InboxNotification): void {
    if (notification.read_at === null) markRead.mutate(notification.id);
  }

  return <>
    <PageHeader
      title="Inbox"
      scope="Your notifications"
      description="Assignments, reviews and blockers that involve you, newest first."
      actions={<Button disabled={unread === 0 || markAll.isPending} onClick={() => markAll.mutate()}>{markAll.isPending ? "Marking as read" : "Mark all as read"}</Button>}
    />
    {markAll.isError ? <p role="alert" className="mb-4 rounded-card border border-critical/25 bg-critical-tint p-3 text-body text-critical">{markAll.error.message}</p> : null}
    {markAll.isSuccess && unread === 0 ? <p role="status" className="mb-4 rounded-card border border-ok/20 bg-ok-tint p-3 text-body">All notifications are marked as read.</p> : null}
    {markRead.isError ? <p role="alert" className="mb-4 rounded-card border border-critical/25 bg-critical-tint p-3 text-body text-critical">{markRead.error.message}</p> : null}

    {can("work.manage") ? <ReviewQueue /> : null}

    <Section title="Notifications" description={notifications.data ? `${unread} unread` : undefined}>
      <Card>
        {notifications.isError ? <ErrorState error={notifications.error} onRetry={() => void notifications.refetch()} />
          : notifications.isLoading ? <><LoadingRegion label="Loading notifications" /><SkeletonTable rows={4} /></>
          : rows.length === 0 ? <EmptyState title="Your inbox is empty" description="Assignments, review requests and blockers on your projects appear here." />
          : <ul className="divide-y divide-line" aria-label="Notifications">
            {rows.map(notification => <NotificationItem key={notification.id} notification={notification}
              onOpen={open} onMarkRead={item => markRead.mutate(item.id)} busy={markRead.isPending} />)}
          </ul>}
      </Card>
    </Section>
  </>;
}
