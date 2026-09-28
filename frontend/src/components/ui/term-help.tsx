import { CircleHelp } from "lucide-react";

import { cn } from "@/lib/cn";

export const TERM_DEFINITIONS = {
  health: {
    label: "Health",
    description: "How the recorded work compares with the plan. Green means fewer recorded delivery concerns; Amber means concerns need review; Red means substantial concerns under the scoring rules. No colour guarantees delivery or sets a response deadline.",
  },
  confidence: {
    label: "Data confidence",
    description: "How recently records were updated, how complete they are, whether owners are named, and whether source data is available. It is not a probability of success or a guarantee that the data is correct.",
  },
  gateReadiness: {
    label: "Gate readiness",
    description: "Shows whether recorded gate criteria and evidence are ready for review. Readiness does not approve a gate; human approval is still required.",
  },
  traceState: {
    label: "Trace state",
    description: "Describes a requirement's linked tests and evidence, including recorded test results. A link alone does not prove verification or approval.",
  },
  assumption: {
    label: "Assumption",
    description: "A working premise that needs validating with evidence and an accountable owner. Recording an assumption does not make it a verified fact.",
  },
  analysisDate: {
    label: "Analysis date",
    description: "Defaults to today in UTC. An explicit as-of date evaluates the current records against that date; it does not restore a historical snapshot.",
  },
} as const;

interface TermHelpProps {
  term: keyof typeof TERM_DEFINITIONS;
  className?: string;
}

export function TermHelp({ term, className }: TermHelpProps): JSX.Element {
  const definition = TERM_DEFINITIONS[term];
  return (
    <details className={cn("min-w-0 max-w-full text-meta text-ink-secondary", className)}>
      <summary tabIndex={0} className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-control px-1 font-medium hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        <CircleHelp aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
        About {definition.label.toLowerCase()}
      </summary>
      <p className="mb-2 max-w-prose rounded-control border border-line bg-surface-subtle p-3 text-body leading-relaxed text-ink-secondary">
        {definition.description}
      </p>
    </details>
  );
}