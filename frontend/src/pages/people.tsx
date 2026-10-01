import { useState } from "react";
import type { FormEvent } from "react";

import { AccountActiveControl, PasswordResetControl, RoleControl, SessionRevokeControl } from "@/components/account-controls";
import { DatabaseCard, ProjectRemovalSection } from "@/components/admin/workspace-maintenance";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { ErrorState } from "@/components/ui/error-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, type Tone } from "@/components/ui/status-badge";
import { ApiError, useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useCreateInvitation, useInvitations, useRevokeInvitation, useRoles, useUsers } from "@/lib/queries";
import type { Invitation, RoleDescriptor, User } from "@/types/api";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const INVITATION_TONES: Record<Invitation["status"], Tone> = {
  Pending: "warn",
  Accepted: "ok",
  Revoked: "neutral",
  Expired: "neutral",
};

interface IssuedInvitation {
  email: string;
  link: string;
  expiresAt: string;
}

function invitationLink(code: string, email: string): string {
  return `${window.location.origin}/register?invite=${encodeURIComponent(code)}&email=${encodeURIComponent(email)}`;
}

function InvitationsSection({ roles }: { roles: RoleDescriptor[] }): JSX.Element {
  const { can } = useAuth();
  const invitations = useInvitations(can("user.manage"));
  const create = useCreateInvitation();
  const withdraw = useRevokeInvitation();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState<string | null>(null);
  // The link holds the one-time code, so it lives only here and is gone once dismissed.
  const [issued, setIssued] = useState<IssuedInvitation | null>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);

  async function invite(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    const address = email.trim();
    if (!EMAIL_PATTERN.test(address) || !role) {
      setError("Enter a valid email address and choose a role.");
      return;
    }
    try {
      const result = await create.mutateAsync({ email: address, role });
      setIssued({
        email: result.invitation.email,
        link: invitationLink(result.code, result.invitation.email),
        expiresAt: result.invitation.expires_at,
      });
      setCopyNotice(null);
      setEmail("");
      setRole("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The invitation could not be created.");
    } finally {
      create.reset();
    }
  }

  async function copyLink(link: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(link);
      setCopyNotice("Link copied.");
    } catch {
      setCopyNotice("Copying is blocked in this browser. Select the link and copy it instead.");
    }
  }

  const columns: Column<Invitation>[] = [
    { key: "email", header: "Email", value: (row) => row.email, cell: (row) => <span className="break-all font-medium text-ink">{row.email}</span> },
    { key: "role", header: "Role", value: (row) => row.role_label, cell: (row) => row.role_label },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={INVITATION_TONES[row.status] ?? "neutral"} />,
    },
    {
      key: "invited",
      header: "Invited",
      value: (row) => row.created_at,
      cell: (row) => (
        <div className="min-w-0">
          <p>{formatDate(row.created_at)}</p>
          <p className="truncate text-meta text-ink-secondary">by {row.created_by}</p>
        </div>
      ),
    },
    { key: "expires", header: "Expires", value: (row) => row.expires_at, cell: (row) => formatDate(row.expires_at) },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => row.status === "Pending" ? (
        <Button size="sm" disabled={withdraw.isPending} aria-label={`Withdraw the invitation for ${row.email}`} onClick={() => withdraw.mutate(row.id)}>
          Withdraw
        </Button>
      ) : null,
    },
  ];

  return (
    <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="h-fit">
        <CardHeader title="Invite someone" description="They register through a personal link with the role you choose." />
        <CardBody>
          <form className="space-y-3" onSubmit={(event) => void invite(event)} noValidate>
            <Field label="Email address" htmlFor="invite-email">
              <TextInput id="invite-email" type="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} />
            </Field>
            <Field label="Role" htmlFor="invite-role">
              <Select id="invite-role" value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="">Choose a role</option>
                {roles.map((option) => <option key={option.role} value={option.role}>{option.label}</option>)}
              </Select>
            </Field>
            {error ? <p role="alert" className="text-meta text-critical">{error}</p> : null}
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? "Inviting" : "Invite"}
            </Button>
          </form>
          {issued ? (
            <div role="status" className="mt-4 space-y-3 rounded-card border border-ok/20 bg-ok-tint p-3">
              <p className="text-body text-ink">Invitation created for {issued.email}. Send them this link privately.</p>
              <p className="break-all rounded-control border border-line bg-surface-subtle px-3 py-2 font-mono text-meta text-ink">{issued.link}</p>
              <p className="text-meta text-ink-secondary">
                It expires in 7 days, on {formatDate(issued.expiresAt)}, and is shown only once. Withdraw the invitation if it reaches the wrong person.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={() => void copyLink(issued.link)}>Copy link</Button>
                <Button size="sm" variant="ghost" onClick={() => { setIssued(null); setCopyNotice(null); }}>Done</Button>
              </div>
              {copyNotice ? <p className="text-meta text-ink-secondary">{copyNotice}</p> : null}
            </div>
          ) : null}
        </CardBody>
      </Card>
      <div className="min-w-0 space-y-2 lg:col-span-2">
        <DataTable
          label="Invitations"
          rows={invitations.data}
          columns={columns}
          rowKey={(row) => String(row.id)}
          isLoading={invitations.isLoading}
          error={invitations.isError ? invitations.error : undefined}
          onRetry={() => void invitations.refetch()}
          searchPlaceholder="Filter invitations"
          emptyTitle="No invitations"
          emptyDescription="Invitations you send appear here with their status."
        />
        {withdraw.isError ? <p role="alert" className="text-body text-critical">{withdraw.error.message}</p> : null}
      </div>
    </div>
  );
}

const COLUMNS: Column<User>[] = [
  {
    key: "person",
    header: "Person",
    value: (row) => row.full_name,
    cell: (row) => (
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{row.full_name}</p>
        <p className="truncate text-meta text-ink-secondary">{row.email}</p>
      </div>
    ),
  },
  {
    key: "title",
    header: "Job title",
    value: (row) => row.job_title ?? "",
    cell: (row) => row.job_title ?? "Not recorded",
  },
  {
    key: "status",
    header: "Status",
    value: (row) => (row.is_active ? "Active" : "Disabled"),
    cell: (row) => (
      <StatusBadge label={row.is_active ? "Active" : "Disabled"} tone={row.is_active ? "ok" : "neutral"} />
    ),
  },
  {
    key: "last_login",
    header: "Last sign-in",
    align: "right",
    value: (row) => row.last_login_at ?? "",
    cell: (row) => formatDate(row.last_login_at),
  },
];

export function PeoplePage(): JSX.Element {
  const { user, can } = useAuth();
  const users = useUsers(can("user.manage"));
  const roles = useRoles(can("user.manage"));
  const columns: Column<User>[] = [
    COLUMNS[0]!,
    { key: "role", header: "Role assignment", value: person => person.role_label, cell: person => <RoleControl person={person} roles={roles.data ?? []} isSelf={person.id === user?.id} /> },
    ...COLUMNS.slice(1),
    { key: "actions", header: "Access", cell: person => <div className="flex flex-wrap gap-2"><AccountActiveControl person={person} isSelf={person.id === user?.id} /><PasswordResetControl person={person} isSelf={person.id === user?.id} /><SessionRevokeControl person={person} isSelf={person.id === user?.id} /></div> },
  ];

  if (!can("user.manage")) return <PageHeader title="Team & Access" description="An Administrator manages account roles. PMs and PMO Analysts manage project membership in each project's Team members tab." />;

  return (
    <>
      <PageHeader
        title="Team & Access"
        description="Choose a person's role from the dropdown, then confirm the change. Project access is managed in each project's Team members tab."
      />
      {roles.isError ? <ErrorState error={roles.error} onRetry={() => void roles.refetch()} /> : null}
      <DataTable
        rows={users.data}
        columns={columns}
        rowKey={(row) => String(row.id)}
        isLoading={users.isLoading}
        error={users.isError ? users.error : undefined}
        onRetry={() => void users.refetch()}
        searchPlaceholder="Filter people"
        emptyTitle="No accounts"
        emptyDescription="Accounts created in EPOS appear here."
      />
      <InvitationsSection roles={roles.data ?? []} />
      <DatabaseCard />
      <ProjectRemovalSection />
    </>
  );
}
