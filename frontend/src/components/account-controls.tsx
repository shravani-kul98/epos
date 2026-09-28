import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select } from "@/components/ui/form";
import { useResetUserPassword, useRevokeUserSessions, useSetUserActive, useSetUserRole } from "@/lib/queries";
import { ROLE_GUIDES } from "@/lib/terminology";
import type { RoleDescriptor, User } from "@/types/api";

export function RoleControl({ person, roles, isSelf }: { person: User; roles: RoleDescriptor[]; isSelf: boolean }): JSX.Element {
  const id = useId();
  const [selected, setSelected] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState("");
  const changeRole = useSetUserRole();
  const nextRole = selected ?? person.role;
  const label = roles.find(role => role.role === nextRole)?.label ?? person.role_label;
  const guide = ROLE_GUIDES[nextRole];

  async function confirm(): Promise<void> {
    if (!selected || isSelf) return;
    try {
      await changeRole.mutateAsync({ userId: person.id, role: selected });
      setNotice(`Role saved: ${label}.`);
      setSelected(null);
      setConfirming(false);
    } catch {
      // The server refusal is shown in the confirmation panel.
    }
  }

  return <div className="min-w-48 space-y-2">
    <Field label="EPOS role" htmlFor={id}><Select id={id} aria-label={`Role for ${person.full_name} (${person.email})`} value={nextRole}
      disabled={isSelf || roles.length === 0 || changeRole.isPending}
      onChange={event => { setSelected(event.target.value); setNotice(""); changeRole.reset(); }}>
      {roles.length ? roles.map(role => <option key={role.role} value={role.role}>{role.label}</option>) : <option value={person.role}>{person.role_label}</option>}
    </Select></Field>
    {isSelf ? <p className="text-meta text-ink-secondary">Your administrator access is protected.</p> : <Button size="sm" disabled={!selected || selected === person.role || changeRole.isPending} onClick={() => setConfirming(true)}>Save role</Button>}
    {notice ? <p role="status" className="text-meta text-ok">{notice}</p> : null}
    <Drawer open={confirming} onClose={() => setConfirming(false)} busy={changeRole.isPending} title="Confirm role change" description={`${person.full_name} · ${person.email}`}
      footer={close => <><Button onClick={close}>Cancel</Button><Button variant="primary" disabled={changeRole.isPending || isSelf} onClick={() => void confirm()}>{changeRole.isPending ? "Saving" : "Confirm role change"}</Button></>}>
      <p className="text-body">Change from <strong>{person.role_label}</strong> to <strong>{label}</strong>?</p>
      {guide ? <p className="mt-3 text-body text-ink-secondary">{guide.summary}</p> : null}
      <p className="mt-3 text-body text-ink-secondary">This changes what the account may do. Project membership is managed separately. The change is audited and the backend enforces it immediately.</p>
      {changeRole.isError ? <p role="alert" className="mt-4 text-body text-critical">{changeRole.error.message}</p> : null}
    </Drawer>
  </div>;
}

export function AccountActiveControl({ person, isSelf }: { person: User; isSelf: boolean }): JSX.Element {
  const [confirming, setConfirming] = useState(false);
  const changeActive = useSetUserActive();
  async function confirm(): Promise<void> {
    if (isSelf) return;
    try {
      await changeActive.mutateAsync({ userId: person.id, isActive: !person.is_active });
      setConfirming(false);
    } catch {
      // Failed access changes must remain visible and must not update the account locally.
    }
  }
  return <>
    <Button size="sm" disabled={isSelf} onClick={() => { changeActive.reset(); setConfirming(true); }}>{person.is_active ? "Disable account" : "Enable account"}</Button>
    <Drawer open={confirming} onClose={() => setConfirming(false)} busy={changeActive.isPending} title={person.is_active ? "Disable this account?" : "Enable this account?"} description={`${person.full_name} · ${person.email}`}
      footer={close => <><Button onClick={close}>Cancel</Button><Button variant={person.is_active ? "danger" : "primary"} disabled={changeActive.isPending || isSelf} onClick={() => void confirm()}>{changeActive.isPending ? "Saving" : "Confirm account change"}</Button></>}>
      <p className="text-body text-ink-secondary">{person.is_active ? "This blocks access without deleting the account or its audit history. EPOS refuses while the person still has open assigned tasks, so reassign or complete them first." : "This restores access according to the account's existing role and project memberships."}</p>
      {changeActive.isError ? <p role="alert" className="mt-4 text-body text-critical">{changeActive.error.message}</p> : null}
    </Drawer>
  </>;
}

export function PasswordResetControl({ person, isSelf }: { person: User; isSelf: boolean }): JSX.Element {
  const [confirming, setConfirming] = useState(false);
  const [temporary, setTemporary] = useState<string | null>(null);
  const reset = useResetUserPassword();
  async function confirm(): Promise<void> {
    if (isSelf) return;
    try {
      setTemporary((await reset.mutateAsync(person.id)).temporary_password);
    } catch {
      // The refusal is shown in the panel.
    }
  }
  function close(): void {
    // The temporary password is held only while this panel is open.
    setTemporary(null);
    reset.reset();
    setConfirming(false);
  }
  return <>
    <Button size="sm" disabled={isSelf} onClick={() => { reset.reset(); setTemporary(null); setConfirming(true); }}>Reset password</Button>
    <Drawer open={confirming} onClose={close} busy={reset.isPending} title={temporary ? "Temporary password issued" : "Reset this password?"} description={`${person.full_name} · ${person.email}`}
      footer={() => temporary
        ? <Button variant="primary" onClick={close}>Done</Button>
        : <><Button onClick={close}>Cancel</Button><Button variant="danger" disabled={reset.isPending || isSelf} onClick={() => void confirm()}>{reset.isPending ? "Resetting" : "Confirm password reset"}</Button></>}>
      {temporary ? <div role="status" className="space-y-3">
        <p className="text-body">Give {person.full_name} this temporary password privately. It is shown only once.</p>
        <p className="break-all rounded-control border border-line bg-surface-subtle px-3 py-2 font-mono text-body text-ink">{temporary}</p>
        <p className="text-meta text-ink-secondary">When they sign in with it, EPOS asks them to choose their own password before they can do anything else.</p>
      </div> : <p className="text-body text-ink-secondary">This replaces the current password with a temporary one and ends the person&apos;s existing sessions. The reset is recorded in the audit trail; the temporary password is not.</p>}
      {reset.isError ? <p role="alert" className="mt-4 text-body text-critical">{reset.error.message}</p> : null}
    </Drawer>
  </>;
}

export function SessionRevokeControl({ person, isSelf }: { person: User; isSelf: boolean }): JSX.Element {
  const [confirming, setConfirming] = useState(false);
  const [ended, setEnded] = useState(false);
  const revoke = useRevokeUserSessions();
  async function confirm(): Promise<void> {
    if (isSelf) return;
    try {
      await revoke.mutateAsync(person.id);
      setEnded(true);
    } catch {
      // The refusal is shown in the panel.
    }
  }
  function close(): void {
    setEnded(false);
    revoke.reset();
    setConfirming(false);
  }
  return <>
    <Button size="sm" disabled={isSelf} onClick={() => { revoke.reset(); setEnded(false); setConfirming(true); }}>End sessions</Button>
    <Drawer open={confirming} onClose={close} busy={revoke.isPending} title={ended ? "Sessions ended" : "End every session?"} description={`${person.full_name} · ${person.email}`}
      footer={() => ended
        ? <Button variant="primary" onClick={close}>Done</Button>
        : <><Button onClick={close}>Cancel</Button><Button variant="danger" disabled={revoke.isPending || isSelf} onClick={() => void confirm()}>{revoke.isPending ? "Ending sessions" : "Confirm end sessions"}</Button></>}>
      {ended
        ? <p role="status" className="text-body">{person.full_name} is signed out of every browser and client. Their password is unchanged, so they can sign in again.</p>
        : <p className="text-body text-ink-secondary">This signs {person.full_name} out of every browser and client at once, for example after a lost device. The account and its password stay as they are. The action is recorded in the audit trail.</p>}
      {revoke.isError ? <p role="alert" className="mt-4 text-body text-critical">{revoke.error.message}</p> : null}
    </Drawer>
  </>;
}
