import { Link } from "react-router-dom";
import { Drawer } from "@/components/ui/drawer";
import { ErrorState } from "@/components/ui/error-state";
import { SkeletonTable } from "@/components/ui/loading-skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { useWorkspaceSearch } from "@/lib/queries";
import { recordTypeLabel } from "@/lib/terminology";
import type { EvidenceRecord } from "@/types/api";

const TITLE_FIELDS = ["project_name", "risk_name", "milestone_name", "task_name", "requirement_text", "change_description", "action_description", "title"];

export function EvidenceDrawer({ records, reference, onClose }: {
  records?: EvidenceRecord[];
  reference?: string;
  onClose: () => void;
}): JSX.Element {
  const search = useWorkspaceSearch(reference ?? "");
  const exact = search.data?.hits.filter((hit) => hit.record_id === reference) ?? [];
  return <Drawer open onClose={onClose} title={reference ? `Source ${reference}` : "Evidence used"} description="Authorized records supporting this view. References do not grant access to other records." width="max-w-2xl">
    {reference ? search.isError ? <ErrorState error={search.error} onRetry={() => void search.refetch()} /> : search.isLoading ? <SkeletonTable rows={3} /> : (
      <div className="space-y-3">
        {exact.map((hit) => <article key={`${hit.record_type}-${hit.record_id}`} className="rounded-control border border-line p-4">
          <StatusBadge label={hit.record_type_label} tone="accent" />
          <h3 className="mt-3 text-card font-medium">{hit.title}</h3>
          <p className="mt-1 text-meta text-ink-secondary">{hit.project_name} · <code>{hit.record_id}</code></p>
          {hit.subtitle ? <p className="mt-2 text-body text-ink-secondary">{hit.subtitle}</p> : null}
          <Link to={hit.path} onClick={onClose} className="mt-3 inline-flex min-h-10 items-center text-body font-medium text-accent hover:underline">Open supporting record</Link>
        </article>)}
        {!exact.length ? <p className="text-body text-ink-secondary">No accessible stored record matches this reference. Review the supplied calculation or the related project; the reference may identify a calculated result.</p> : null}
      </div>
    ) : null}
    {records ? <ul className="space-y-5">{records.map((record) => {
      const titleKey = TITLE_FIELDS.find((key) => Boolean(record.fields[key]));
      return <li key={`${record.record_type}-${record.record_id}`} className="border-b border-line pb-5 last:border-0">
        <h3 className="text-card font-medium">{titleKey ? record.fields[titleKey] : record.record_id}</h3>
        <p className="mt-1 text-meta text-ink-muted">{recordTypeLabel(record.record_type)} · <code>{record.record_id}</code></p>
        <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">{Object.entries(record.fields).filter(([key]) => key !== titleKey).map(([key, value]) => <div key={key} className="min-w-0">
          <dt className="text-meta text-ink-secondary">{recordTypeLabel(key)}</dt>
          <dd className="mt-1 break-words text-body text-ink">{value || "Not recorded"}</dd>
        </div>)}</dl>
      </li>;
    })}</ul> : null}
  </Drawer>;
}