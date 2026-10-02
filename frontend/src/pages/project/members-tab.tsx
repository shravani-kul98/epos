import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select } from "@/components/ui/form";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { useAddProjectMember, useMemberCandidates, useProjectMembers, useRemoveProjectMember, useUpdateProjectMember } from "@/lib/queries";
import { ROLE_GUIDES } from "@/lib/terminology";
import type { ProjectMember } from "@/types/api";

const RESPONSIBILITIES = ["Contributor", "Project lead", "Reviewer"];

export function MembersTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const allowed = can("project_members.manage");
  const members = useProjectMembers(projectId, allowed);
  const [mode, setMode] = useState<"add" | "edit" | "remove" | null>(null);
  const candidates = useMemberCandidates(projectId, allowed && mode === "add");
  const add = useAddProjectMember(projectId);
  const edit = useUpdateProjectMember(projectId);
  const remove = useRemoveProjectMember(projectId);
  const [selected, setSelected] = useState<ProjectMember | null>(null);
  const [person, setPerson] = useState("");
  const [responsibility, setResponsibility] = useState("Contributor");
  const [notice, setNotice] = useState("");
  const formId = useId();
  const mutation = mode === "remove" ? remove : mode === "edit" ? edit : add;

  function open(next: "add" | "edit" | "remove", member?: ProjectMember): void {
    add.reset(); edit.reset(); remove.reset();
    setSelected(member ?? null);
    setPerson("");
    setResponsibility(member?.project_role ?? "Contributor");
    setMode(next);
  }

  async function save(): Promise<void> {
    try {
      if (mode === "add") await add.mutateAsync({ user_id: Number(person), project_role: responsibility });
      if (mode === "edit" && selected) await edit.mutateAsync({ userId: selected.user_id, project_role: responsibility });
      if (mode === "remove" && selected) await remove.mutateAsync(selected.user_id);
      setNotice(mode === "remove" ? "Project access removed." : mode === "add" ? "Project member added. Eligible members can now be selected when assigning tasks." : "Project responsibility updated.");
      setMode(null);
    } catch {
      // Membership errors remain visible without discarding the selection.
    }
  }

  const columns: Column<ProjectMember>[] = [
    { key: "person", header: "Person", value: member => `${member.full_name} ${member.email}`, cell: member => <div><p className="font-medium">{member.full_name}</p><p className="text-meta text-ink-secondary">{member.email}</p></div> },
    { key: "role", header: "EPOS role", value: member => ROLE_GUIDES[member.workspace_role]?.label ?? "Unknown role", cell: member => ROLE_GUIDES[member.workspace_role]?.label ?? "Unknown role" },
    { key: "responsibility", header: "Project responsibility", value: member => member.project_role, cell: member => member.project_role },
    { key: "active", header: "Account", cell: member => <StatusBadge label={member.is_active ? "Active" : "Disabled"} tone={member.is_active ? "ok" : "neutral"} /> },
    { key: "actions", header: "Actions", cell: member => <div className="flex flex-wrap gap-2"><Button size="sm" onClick={() => open("edit", member)}>Edit responsibility</Button><Button size="sm" onClick={() => open("remove", member)}>Remove access</Button></div> },
  ];
  const responsibilities = RESPONSIBILITIES.includes(responsibility) ? RESPONSIBILITIES : [responsibility, ...RESPONSIBILITIES];

  if (!allowed) return <p>Your role cannot manage project membership.</p>;

  return <div className="space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-section font-semibold">Team members</h2><p className="mt-1 text-body text-ink-secondary">Add a registered person to this project, then assign tasks from Delivery plan.</p></div><Button variant="primary" onClick={() => open("add")}>Add member</Button></div>
    <p className="text-meta text-ink-secondary">Project membership controls access. The EPOS role controls permissions and can be changed only by an Administrator in Team &amp; Access. Project responsibility is a label, not a permission grant.</p>
    {notice ? <p role="status" className="rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
    <DataTable label="Project members" rows={members.data} columns={columns} rowKey={member => String(member.user_id)} isLoading={members.isLoading} error={members.error} onRetry={() => void members.refetch()} searchPlaceholder="Filter members" emptyTitle="No members added" emptyDescription="Add people so tasks can be assigned to their accounts." />
    <Drawer open={mode !== null} onClose={() => setMode(null)} title={mode === "add" ? "Add project member" : mode === "remove" ? "Remove project access?" : "Edit project responsibility"} description={selected ? `${selected.full_name} · ${selected.email}` : undefined}
      busy={mutation.isPending} dirty={mode === "add" ? Boolean(person) : mode === "edit" && responsibility !== selected?.project_role}
      footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant={mode === "remove" ? "danger" : "primary"} disabled={mutation.isPending || (mode === "add" && (!person || candidates.isError))}>{mutation.isPending ? "Saving" : mode === "add" ? "Add to project" : mode === "remove" ? "Confirm removal" : "Save responsibility"}</Button></>}>
      <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
        {mode === "add" ? <>
          <Field label="Person" htmlFor="project-member-person"><Select id="project-member-person" required value={person} onChange={event => setPerson(event.target.value)} disabled={candidates.isLoading || candidates.isError}><option value="">{candidates.isLoading ? "Loading registered accounts" : "Choose a person"}</option>{(candidates.data ?? []).map(candidate => <option key={candidate.user_id} value={candidate.user_id}>{candidate.full_name} · {candidate.email} · {candidate.role_label}</option>)}</Select></Field>
          {candidates.isError ? <div role="alert"><p className="text-critical">{candidates.error.message}</p><Button onClick={() => void candidates.refetch()}>Retry accounts</Button></div> : null}
          {candidates.data?.length === 0 ? <p className="text-body text-ink-secondary">No additional active accounts are available. The person must register first; an Administrator can enable a disabled account.</p> : null}
        </> : null}
        {mode === "remove" ? <p className="text-body text-ink-secondary">This removes project membership, not the account. Open tasks must be reassigned or completed first. Portfolio-wide roles retain their role-based access.</p> : <Field label="Project responsibility" htmlFor="project-member-responsibility"><Select id="project-member-responsibility" value={responsibility} onChange={event => setResponsibility(event.target.value)}>{responsibilities.map(value => <option key={value}>{value}</option>)}</Select></Field>}
        {mutation.isError ? <p role="alert" className="text-body text-critical">{mutation.error.message}</p> : null}
      </form>
    </Drawer>
  </div>;
}
