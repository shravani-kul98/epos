import { PageHeader } from "@/components/ui/page-header";
import { DecisionsTab } from "@/pages/project/decisions-tab";

export function DecisionsPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Decisions"
        description="Every decision taken across the portfolio, with the reasoning behind it and the records it relates to."
      />
      <DecisionsTab showProjectColumn />
    </>
  );
}
