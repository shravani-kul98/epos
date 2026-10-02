import { useState } from "react";
import { Plus } from "lucide-react";

import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { RequirementFormDrawer } from "@/components/requirement-form-drawer";
import { RequirementRegister } from "@/components/requirement-register";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/ui/metric-card";
import { useAuth } from "@/lib/auth";
import { formatPercent } from "@/lib/format";
import { useTraceability } from "@/lib/queries";

export function RequirementsTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const traceability = useTraceability(projectId);
  const data = traceability.data;
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");

  return (
    <div className="space-y-4">
      {can("requirement.manage") ? (
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="primary" onClick={() => { setNotice(""); setCreating(true); }}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            New requirement
          </Button>
        </div>
      ) : null}
      {notice ? <p role="status" className="rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard
          label="Requirements"
          value={data?.total_requirements ?? "—"}
          caption="Recorded against this project"
        />
        <MetricCard
          label="Verified coverage"
          value={data ? formatPercent(data.coverage_percent) : "—"}
          caption="Requirements with a verified linked test"
        />
        <MetricCard
          label="Open change requests"
          value={data ? data.rows.reduce((total, row) => total + row.open_change_request_ids.length, 0) : "—"}
          caption="Awaiting a recorded decision"
        />
      </div>

      {data && Object.keys(data.status_counts).length > 0 ? (
        <Card>
          <CardHeader title="Verification position" description="Evidence states supplied by the traceability service" />
          <CardBody className="flex flex-wrap gap-2">
            {Object.entries(data.status_counts).map(([status, count]) => (
              <span
                key={status}
                className="inline-flex items-center gap-2 rounded-full border border-line bg-surface-subtle px-2.5 py-1 text-meta text-ink"
              >
                {status}
                <span className="font-semibold" data-numeric>
                  {count}
                </span>
              </span>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <RequirementRegister
        rows={data?.rows}
        isLoading={traceability.isLoading}
        error={traceability.isError ? traceability.error : undefined}
        onRetry={() => void traceability.refetch()}
        projectId={projectId}
      />

      {creating ? (
        <RequirementFormDrawer
          projectId={projectId}
          onClose={() => setCreating(false)}
          onSaved={(requirement) => setNotice(`Requirement ${requirement.requirement_id} created. Open it to link the work and tests that realise it.`)}
        />
      ) : null}
    </div>
  );
}
