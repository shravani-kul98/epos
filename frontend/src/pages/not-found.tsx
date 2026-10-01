import { useNavigate } from "react-router-dom";

import { homeLabelFor } from "@/components/layout/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { useAuth } from "@/lib/auth";

export function NotFoundPage(): JSX.Element {
  const navigate = useNavigate();
  const { can } = useAuth();
  const home = homeLabelFor(can).toLowerCase();
  return (
    <>
    <PageHeader
      title="Page not found"
      description="That address does not match an EPOS page. No project information has changed."
    />
    <Card>
      <EmptyState
        headingLevel={2}
        title="Return to your workspace"
        description={`Use the navigation to choose a page, or return to the ${home}.`}
        action={
          <Button variant="primary" onClick={() => navigate("/")}>Back to {home}</Button>
        }
      />
    </Card>
    </>
  );
}
