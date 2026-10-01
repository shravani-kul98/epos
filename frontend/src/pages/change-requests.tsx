import { PageHeader } from "@/components/ui/page-header";
import { ChangesTab } from "@/pages/project/changes-tab";

export function ChangeRequestsPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Change requests"
        description="Every request to change a requirement, with the downstream impact EPOS calculates before a decision is recorded."
      />
      <ChangesTab showProjectColumn />
    </>
  );
}
