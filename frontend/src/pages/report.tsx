import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingRegion, SkeletonCards } from "@/components/ui/loading-skeleton";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { SourceList } from "@/components/ui/source-list";
import { cn } from "@/lib/cn";
import { useExecutiveReport } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { ExecutiveReport } from "@/types/api";

const WINDOWS = [
  { days: 7, label: "This week" },
  { days: 14, label: "Two weeks" },
  { days: 30, label: "This month" },
  { days: 90, label: "This quarter" },
] as const;

/** Plain text, so the report can be pasted into an email without losing its structure. */
export function reportAsText(report: ExecutiveReport): string {
  const lines = [
    `Executive report as at ${report.as_of_date}`,
    "",
    report.headline,
    "",
    `Health: ${report.health_bands.green} green, ${report.health_bands.amber} amber, ${report.health_bands.red} red.`,
    `Alerts: ${report.alert_severities.critical} critical, ${report.alert_severities.high} high.`,
  ];

  for (const section of report.sections) {
    lines.push("", section.title.toUpperCase(), section.summary);
    for (const item of section.items) {
      lines.push(`- ${item.text} [${item.source_ids.join(", ")}]`);
    }
  }

  lines.push("", "Every statement above is drawn from recorded project data.");
  return lines.join("\n");
}

function CopyButton({ report }: { report: ExecutiveReport }): JSX.Element {
  const [copied, setCopied] = useState(false);
  const [copyError,setCopyError]=useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(reportAsText(report));
      setCopied(true);
      setCopyError(false);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
      setCopyError(true);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
    <Button variant="primary" onClick={() => void copy()}>
      {copied ? (
        <Check aria-hidden="true" className="h-3.5 w-3.5" />
      ) : (
        <Copy aria-hidden="true" className="h-3.5 w-3.5" />
      )}
      {copied ? "Copied" : "Copy report"}
    </Button>
    {copyError?<span role="status" className="text-meta text-ink-secondary">Copy was unavailable. Select the report text to copy it.</span>:null}
    </div>
  );
}

/** A report assembled from authoritative records, with its reporting window kept shareable. */
export function ReportPage(): JSX.Element {
  const { params, update }=useViewParams();
  const requestedDays=Number(params.get("days"));
  const days=WINDOWS.some(window=>window.days===requestedDays)?requestedDays:7;
  const report = useExecutiveReport(days);

  return (
    <>
      <PageHeader
        title="Executive report"
        description="Assembled from calculated scores and recorded history. Nothing on this page is generated text."
        asOfDate={report.data?.as_of_date}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap items-center gap-1 rounded-control border border-line bg-surface p-0.5">
              {WINDOWS.map((window) => (
                <button
                  key={window.days}
                  type="button"
                  onClick={() => update({days:String(window.days)})}
                  aria-pressed={days === window.days}
                  className={cn(
                    "min-h-9 rounded px-2.5 py-1 text-meta font-medium",
                    days === window.days
                      ? "bg-accent-tint text-accent"
                      : "text-ink-secondary hover:text-ink",
                  )}
                >
                  {window.label}
                </button>
              ))}
            </div>
            {report.data ? <CopyButton report={report.data} /> : null}
          </div>
        }
      />

      {report.isError ? (
        <Card>
          <ErrorState error={report.error} onRetry={() => void report.refetch()} />
        </Card>
      ) : report.isLoading || !report.data ? (
        <>
          <LoadingRegion label="Assembling the report" />
          <SkeletonCards />
        </>
      ) : (
        <>
          <Card className="mb-4">
            <CardBody>
              <p className="text-section font-semibold text-ink">{report.data.headline}</p>
              <p className="mt-1 text-meta text-ink-muted">
                Covering the last {report.data.window_days} days, as at {report.data.as_of_date}.
              </p>
            </CardBody>
          </Card>

          <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Projects" value={report.data.project_count} caption="In the portfolio" />
            <MetricCard
              label="Red band"
              value={report.data.health_bands.red}
              caption={`${report.data.health_bands.amber} amber · ${report.data.health_bands.green} green`}
            />
            <MetricCard
              label="Critical alerts"
              value={report.data.alert_severities.critical}
              caption={`${report.data.alert_severities.high} high`}
            />
            <MetricCard
              label="Low confidence"
              value={report.data.confidence_bands.low}
              caption="Projects reporting on weak information"
            />
          </div>

          {report.data.sections.length === 0 ? (
            <Card>
              <EmptyState
                title="Nothing to report"
                description="No project is in the red band, no severe alert is open and nothing moved in this window."
                className="py-10"
              />
            </Card>
          ) : (
            <div className="space-y-4">
              {report.data.sections.map((section) => (
                <Card key={section.key}>
                  <CardHeader title={section.title} description={section.summary} />
                  <ul className="divide-y divide-line">
                    {section.items.map((item) => (
                      <li key={item.text} className="px-4 py-3">
                        <p className="text-body text-ink">{item.text}</p>
                        <SourceList ids={item.source_ids} className="mt-1.5" />
                      </li>
                    ))}
                  </ul>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
