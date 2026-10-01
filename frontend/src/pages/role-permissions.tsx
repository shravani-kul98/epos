import { useState } from "react";
import type { FormEvent } from "react";
import { Check, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Field, TextInput } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { WORKSPACE_NAME } from "@/config";
import { ApiError, useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { useChangePassword, useRevokeOtherSessions, useRevokeSession, useSessions } from "@/lib/queries";
import { roleGuide } from "@/lib/terminology";
import type { SessionInfo } from "@/types/api";

const MIN_PASSWORD_LENGTH = 12;
const DEVICE_LABEL_LENGTH = 60;
const BROWSERS: Array<[string, string]> = [
  ["Edg/", "Edge"], ["OPR/", "Opera"], ["Firefox/", "Firefox"], ["Chrome/", "Chrome"], ["Safari/", "Safari"],
];
const SYSTEMS: Array<[string, string]> = [
  ["Windows", "Windows"], ["iPhone", "iOS"], ["iPad", "iPadOS"], ["Android", "Android"],
  ["CrOS", "ChromeOS"], ["Mac OS X", "macOS"], ["Linux", "Linux"],
];

function labelFor(userAgent: string, markers: Array<[string, string]>): string | undefined {
  return markers.find(([marker]) => userAgent.includes(marker))?.[1];
}

/** A short, recognisable name for the browser or client behind a session. */
function describeDevice(userAgent: string | null): string {
  if (!userAgent) return "Unknown device";
  const browser = labelFor(userAgent, BROWSERS);
  const system = labelFor(userAgent, SYSTEMS);
  if (browser || system) return [browser, system].filter(Boolean).join(" on ");
  return userAgent.length > DEVICE_LABEL_LENGTH ? `${userAgent.slice(0, DEVICE_LABEL_LENGTH - 1)}…` : userAgent;
}

function PasswordChangeCard(): JSX.Element {
  const { user, signIn, signOut } = useAuth();
  const changePassword = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!user) return;
    if (!current || next.length < MIN_PASSWORD_LENGTH) {
      setError(`Enter your current password and a new one of at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setError("Both new passwords must match.");
      return;
    }
    try {
      await changePassword.mutateAsync({ current_password: current, new_password: next });
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 403
          ? "Your current password is not correct."
          : caught instanceof ApiError
            ? caught.message
            : "Your password could not be changed.",
      );
      return;
    }
    // The change ends every session of the account, this one included, so sign straight back in.
    try {
      await signIn(user.email, next);
    } catch {
      void signOut();
      return;
    }
    setCurrent("");
    setNext("");
    setConfirm("");
    setNotice("Password changed. Sessions signed in with the old password have ended.");
  }

  return (
    <Card className="h-fit">
      <CardHeader title="Password" description="Changing it signs out every other session." />
      <CardBody>
        <form className="space-y-3" onSubmit={(event) => void submit(event)} noValidate>
          <Field label="Current password" htmlFor="current-password">
            <TextInput id="current-password" type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} />
          </Field>
          <Field label="New password" htmlFor="new-password" hint={`At least ${MIN_PASSWORD_LENGTH} characters, with some variety.`}>
            <TextInput id="new-password" type="password" autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} />
          </Field>
          <Field label="Confirm new password" htmlFor="confirm-password">
            <TextInput id="confirm-password" type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} />
          </Field>
          {error ? <p role="alert" className="text-meta text-critical">{error}</p> : null}
          {notice ? <p role="status" className="text-meta text-ok">{notice}</p> : null}
          <Button type="submit" variant="primary" disabled={changePassword.isPending}>
            {changePassword.isPending ? "Changing" : "Change password"}
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function SessionsCard(): JSX.Element {
  const { status } = useAuth();
  const sessions = useSessions(status === "authenticated");
  const revoke = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();
  const [notice, setNotice] = useState<string | null>(null);
  const others = (sessions.data ?? []).filter((session) => !session.current).length;
  const busy = revoke.isPending || revokeOthers.isPending;
  const failure = revoke.error ?? revokeOthers.error;

  async function endSession(session: SessionInfo): Promise<void> {
    setNotice(null);
    revokeOthers.reset();
    try {
      await revoke.mutateAsync(session.id);
      setNotice(`${describeDevice(session.user_agent)} was signed out.`);
    } catch {
      // The refusal is shown under the list.
    }
  }

  async function endOtherSessions(): Promise<void> {
    setNotice(null);
    revoke.reset();
    try {
      await revokeOthers.mutateAsync();
      setNotice("Every other session was signed out.");
    } catch {
      // The refusal is shown under the list.
    }
  }

  return (
    <Card className="h-fit lg:col-span-2">
      <CardHeader title="Active sessions" description="Browsers and devices signed in to your account." />
      <CardBody>
        {sessions.isError ? (
          <ErrorState error={sessions.error} onRetry={() => void sessions.refetch()} />
        ) : !sessions.data ? (
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : sessions.data.length === 0 ? (
          <p className="text-body text-ink-secondary">No active sessions are recorded for your account.</p>
        ) : (
          <ul className="divide-y divide-line">
            {sessions.data.map((session) => {
              const device = describeDevice(session.user_agent);
              return (
                <li key={session.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-body font-medium text-ink">
                      <span className="break-words" title={session.user_agent ?? undefined}>{device}</span>
                      {session.current ? <StatusBadge label="This device" tone="accent" /> : null}
                    </p>
                    <p className="mt-0.5 text-meta text-ink-secondary">
                      Last active {formatDateTime(session.last_seen_at)} · Signed in {formatDateTime(session.created_at)}
                    </p>
                  </div>
                  {session.current ? null : (
                    <Button
                      size="sm"
                      disabled={busy}
                      aria-label={`Sign out ${device}, last active ${formatDateTime(session.last_seen_at)}`}
                      onClick={() => void endSession(session)}
                    >
                      Sign out
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {notice ? <p role="status" className="mt-3 text-meta text-ok">{notice}</p> : null}
        {failure ? <p role="alert" className="mt-3 text-meta text-critical">{failure.message}</p> : null}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <p className="text-meta text-ink-secondary">Signing a session out ends it on that device straight away.</p>
          <Button size="sm" disabled={busy || others === 0} onClick={() => void endOtherSessions()}>
            {revokeOthers.isPending ? "Signing out" : "Sign out all other sessions"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

export function RolePermissionsPage(): JSX.Element {
  const { user } = useAuth();
  const guide = user ? roleGuide(user.role) : undefined;

  return (
    <>
      <PageHeader
        title="Role and permissions"
        description="What your role allows in this workspace."
        meta={
          user ? (
            <>
              <StatusBadge label={user.role_label} tone="accent" />
              <span className="text-meta text-ink-muted">{WORKSPACE_NAME}</span>
            </>
          ) : null
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title={guide?.label ?? user?.role_label ?? "Your role"}
            description={guide?.summary}
          />
          <CardBody className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
                You can
              </h3>
              <ul className="mt-2 space-y-2">
                {(guide?.can ?? []).map((line) => (
                  <li key={line} className="flex gap-2 text-body text-ink">
                    <Check aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
                    {line}
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
                Needs another role
              </h3>
              {(guide?.cannot ?? []).length === 0 ? (
                <p className="mt-2 text-body text-ink-secondary">
                  Your role has full access to this workspace.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {(guide?.cannot ?? []).map((line) => (
                    <li key={line} className="flex gap-2 text-body text-ink-secondary">
                      <Lock aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
                      {line}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardBody>
        </Card>

        <Card className="h-fit">
          <CardHeader title="Your account" />
          <CardBody>
            <dl className="space-y-3">
              {[
                ["Name", user?.full_name ?? "—"],
                ["Email", user?.email ?? "—"],
                ["Job title", user?.job_title ?? "Not recorded"],
                ["Workspace", WORKSPACE_NAME],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-meta text-ink-muted">{label}</dt>
                  <dd className="mt-0.5 break-words text-body text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-4 border-t border-line pt-3 text-meta text-ink-secondary">
              Ask a workspace administrator if your work needs access this role does not include.
            </p>
          </CardBody>
        </Card>

        <PasswordChangeCard />
        <SessionsCard />
      </div>
    </>
  );
}
