import { Layers3 } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { TERM_DEFINITIONS } from "@/components/ui/term-help";
import { PRODUCT_NAME, WORKSPACE_NAME } from "@/config";
import { useAuth } from "@/lib/auth";

interface Destination {
  label: string;
  description: string;
  path: string;
  permission?: string;
}

const MY_WORK: Destination = {
  label: "View my work",
  description: "Review your assigned tasks, update progress and raise blockers. If nothing is assigned, ask your project manager to add you to the team.",
  path: "/my-work",
};

const ROLE_NEXT_STEPS: Record<string, Destination> = {
  engineer: MY_WORK,
  engineering_lead: {
    label: "Review project delivery",
    description: "Open a project's Delivery plan to review milestones, task assignments and blockers.",
    path: "/projects",
    permission: "portfolio.read",
  },
  project_manager: {
    label: "Open your projects",
    description: "Open a project, then use Delivery to review the plan and Team members to organize assignments.",
    path: "/projects",
    permission: "portfolio.read",
  },
  requirements_manager: {
    label: "Review requirements",
    description: "Review requirements and their linked tests and evidence before proposing changes.",
    path: "/requirements",
    permission: "portfolio.read",
  },
  pmo_analyst: {
    label: "Review the portfolio",
    description: "Compare health with data confidence, then open a project to review the supporting records.",
    path: "/portfolio",
    permission: "portfolio.read",
  },
  executive: {
    label: "Review the portfolio",
    description: "Review delivery signals and evidence quality separately before following up on a decision.",
    path: "/portfolio",
    permission: "portfolio.read",
  },
  administrator: {
    label: "Review team access",
    description: "Check workspace roles and access before directing people to their project work.",
    path: "/admin/users",
    permission: "user.manage",
  },
};

export function OnboardingPage(): JSX.Element {
  const { user, can } = useAuth();
  const navigate = useNavigate();
  const suggested = ROLE_NEXT_STEPS[user?.role ?? ""] ?? MY_WORK;
  const nextStep = !suggested.permission || can(suggested.permission) ? suggested : MY_WORK;

  function finish(path: string): void {
    navigate(path, { replace: true });
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-canvas px-4 py-12">
      <div className="w-full max-w-2xl">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="flex h-9 w-9 items-center justify-center rounded-card bg-accent text-ink-onaccent"
            >
              <Layers3 size={20} strokeWidth={1.6} />
            </span>
            <div className="leading-tight">
              <p className="text-card font-semibold text-ink">{PRODUCT_NAME}</p>
              <p className="text-meta text-ink-muted">{WORKSPACE_NAME}</p>
            </div>
          </div>
          <Button variant="ghost" onClick={() => finish("/")}>Go to home</Button>
        </div>

        <div className="card p-6 sm:p-8">
          <h1 className="text-section text-ink">Start with your work</h1>
          <p className="mt-2 text-body text-ink-secondary">
            Signed in as <span className="font-medium text-ink">{user?.role_label ?? "Workspace member"}</span>.
            Your role determines what you can view or change.
          </p>

          <section aria-labelledby="onboarding-next-step" className="mt-5 rounded-card border border-line bg-surface-subtle p-4">
            <h2 id="onboarding-next-step" className="text-card font-semibold text-ink">Your next step</h2>
            <p className="mt-1 text-body text-ink-secondary">{nextStep.description}</p>
            <Button className="mt-4" variant="primary" onClick={() => finish(nextStep.path)}>{nextStep.label}</Button>
          </section>

          <section aria-labelledby="onboarding-signals" className="mt-6">
            <h2 id="onboarding-signals" className="text-card font-semibold text-ink">Read the signals separately</h2>
            <dl className="mt-3 space-y-3">
              {(["health", "confidence", "analysisDate"] as const).map(term => <div key={term}>
                <dt className="text-body font-medium text-ink">{TERM_DEFINITIONS[term].label}</dt>
                <dd className="mt-0.5 text-body text-ink-secondary">{TERM_DEFINITIONS[term].description}</dd>
              </div>)}
            </dl>
          </section>

          <div className="mt-6 flex flex-wrap gap-2">
            {nextStep.path !== MY_WORK.path ? <Button onClick={() => finish(MY_WORK.path)}>View my work</Button> : null}
            {can("project.create") ? <Button onClick={() => finish("/projects/new")}>Create a project</Button> : null}
            <Button variant="ghost" onClick={() => finish("/account/role")}>Role and permissions</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
