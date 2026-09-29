import { useState } from "react";
import { Database, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { ErrorState } from "@/components/ui/error-state";
import { Field, TextInput } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/loading-skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { useApplyDatabaseUpgrade, useDatabaseStatus, useDeleteProject, useProjects } from "@/lib/queries";
import type { Project } from "@/types/api";

/**
 * Where the database stands against this release, with the governed upgrade applied from here.
 * No console access is needed after the first administrator is set up.
 */
export function DatabaseCard(): JSX.Element {
  const status = useDatabaseStatus(true);
  const apply = useApplyDatabaseUpgrade();
  const [confirming, setConfirming] = useState(false);
  const data = status.data;
  const pending = data?.pending ?? [];
  const appPrefix = data?.application_region ? REGION_PREFIXES[data.application_region] : undefined;
  const regionsDiffer = Boolean(appPrefix && data?.database_region?.includes("-") && !data.database_region.startsWith(appPrefix));

  return (
    <Card className="mt-5">
      <CardHeader title="Database" icon={Database}
        description="Schema version and connection health. Upgrades are the governed migrations shipped with this release." />
      <CardBody className="space-y-3">
        {status.isError ? <ErrorState error={status.error} onRetry={() => void status.refetch()} />
          : status.isLoading || !data ? <Skeleton className="h-20 w-full" />
          : <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge label={data.is_current ? "Up to date" : data.current_revision === null ? "Not initialised" : "Upgrade available"}
                tone={data.is_current ? "ok" : "warn"} />
              <span className="text-meta text-ink-secondary">
                Recorded {data.current_revision ?? "none"} · this release expects {data.expected_revision ?? "unknown"}
              </span>
            </div>
            <dl className="grid gap-3 text-body sm:grid-cols-3">
              <div><dt className="text-meta text-ink-secondary">Round trip</dt><dd data-numeric>{data.round_trip_ms === null ? "Not measured" : `${data.round_trip_ms} ms`}</dd></div>
              <div><dt className="text-meta text-ink-secondary">Database region</dt><dd>{data.database_region ?? "Not reported"}</dd></div>
              <div><dt className="text-meta text-ink-secondary">Application region</dt><dd>{data.application_region ?? "Not reported"}</dd></div>
            </dl>
            {regionsDiffer ? <p className="rounded-control border border-warn bg-warn-tint px-3 py-2 text-meta text-ink">
              The application and the database run in different regions, so every query crosses that distance. Moving the application to the database's region makes pages faster.
            </p> : null}
            {pending.length > 0 ? <div>
              <p className="text-meta font-medium text-ink">Pending upgrades</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-meta text-ink-secondary">
                {pending.map(step => <li key={step.revision}>{step.description || step.revision}</li>)}
              </ul>
            </div> : null}
            <p className="text-meta text-ink-secondary">
              {data.automatic_upgrades
                ? "Automatic upgrades are on: the first request after a release applies pending upgrades once, under a database lock."
                : "Automatic upgrades are off. Apply pending upgrades here after each release."}
            </p>
            {data.can_upgrade ? <Button variant="primary" onClick={() => { apply.reset(); setConfirming(true); }}>Apply {pending.length === 1 ? "upgrade" : `${pending.length} upgrades`}</Button> : null}
            {apply.isSuccess ? <p role="status" className="text-meta text-ok">The database is at {apply.data.current_revision}.</p> : null}
          </>}
      </CardBody>
      <Drawer open={confirming} onClose={() => setConfirming(false)} busy={apply.isPending} title="Apply database upgrades?"
        description="Additive schema changes shipped with this release."
        footer={close => <><Button onClick={close}>Cancel</Button><Button variant="primary" disabled={apply.isPending}
          onClick={() => void apply.mutateAsync().then(() => setConfirming(false)).catch(() => undefined)}>{apply.isPending ? "Applying" : "Apply upgrades"}</Button></>}>
        <p className="text-body text-ink-secondary">Upgrades run one at a time under a database lock and are recorded in the audit trail with your name. Existing records are kept. Take a database backup first if your provider offers one.</p>
        {apply.isError ? <p role="alert" className="mt-3 text-body text-critical">{apply.error.message}</p> : null}
      </Drawer>
    </Card>
  );
}

// Hosting regions and the database regions they sit beside, so a cross-region setup can be named.
const REGION_PREFIXES: Record<string, string> = {
  iad1: "us-east-1", cle1: "us-east-2", pdx1: "us-west-2", sfo1: "us-west-1", fra1: "eu-central-1",
  dub1: "eu-west-1", lhr1: "eu-west-2", cdg1: "eu-west-3", arn1: "eu-north-1", sin1: "ap-southeast-1",
  syd1: "ap-southeast-2", hnd1: "ap-northeast-1", bom1: "ap-south-1", gru1: "sa-east-1",
};

/** Withdraw a project with everything recorded against it. Records are retained for audit. */
export function ProjectRemovalSection(): JSX.Element | null {
  const { can } = useAuth();
  const projects = useProjects();
  const remove = useDeleteProject();
  const [target, setTarget] = useState<Project | null>(null);
  const [typed, setTyped] = useState("");
  if (!can("project.delete")) return null;

  const columns: Column<Project>[] = [
    { key: "project", header: "Project", value: row => `${row.project_name} ${row.project_id}`,
      cell: row => <div><p className="font-medium text-ink">{row.project_name}</p><p className="text-meta text-ink-secondary">{row.project_id} · {row.project_manager}</p></div> },
    { key: "phase", header: "Phase", value: row => row.project_phase, cell: row => row.project_phase },
    { key: "remove", header: "Remove", cell: row => <Button size="sm" variant="ghost" onClick={() => { remove.reset(); setTyped(""); setTarget(row); }}><Trash2 size={14} aria-hidden="true" />Remove</Button> },
  ];

  return (
    <Card className="mt-5">
      <CardHeader title="Projects" icon={Trash2} description="Remove test or abandoned projects. Their records leave every view and analysis but stay in the audit trail." />
      <CardBody>
        <DataTable rows={projects.data} columns={columns} rowKey={row => row.project_id} label="Projects that can be removed"
          isLoading={projects.isLoading} error={projects.isError ? projects.error : undefined} onRetry={() => void projects.refetch()}
          searchPlaceholder="Filter projects" emptyTitle="No projects" emptyDescription="Projects appear here once they are created." />
      </CardBody>
      <Drawer open={target !== null} onClose={() => setTarget(null)} busy={remove.isPending} dirty={typed !== ""}
        title={target ? `Remove ${target.project_name}?` : "Remove project"} description={target?.project_id}
        footer={close => <><Button onClick={close}>Cancel</Button><Button variant="danger" disabled={!target || typed.trim() !== target.project_id || remove.isPending}
          onClick={() => { if (target) void remove.mutateAsync(target).then(() => setTarget(null)).catch(() => undefined); }}>{remove.isPending ? "Removing" : "Remove project"}</Button></>}>
        <p className="text-body text-ink-secondary">Its tasks, risks, decisions and every other record leave the product and the portfolio analysis. Members lose access. The records stay in the audit trail.</p>
        {target ? <div className="mt-4"><Field label={`Type ${target.project_id} to confirm`} htmlFor="remove-project-confirm">
          <TextInput id="remove-project-confirm" autoComplete="off" value={typed} onChange={event => setTyped(event.target.value)} />
        </Field></div> : null}
        {remove.isError ? <p role="alert" className="mt-3 text-body text-critical">{remove.error.message}</p> : null}
      </Drawer>
    </Card>
  );
}
