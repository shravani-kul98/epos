import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { lazy, Suspense, type ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingRegion, Skeleton, SkeletonCards } from "@/components/ui/loading-skeleton";
import { RouteErrorBoundary } from "@/components/ui/route-error-boundary";
import { PageHeader } from "@/components/ui/page-header";
import { SaveFeedback } from "@/components/ui/save-feedback";
import { sessionEndedByReader, useAuth } from "@/lib/auth";
import { LoginPage } from "@/pages/login";
import { NotFoundPage } from "@/pages/not-found";
import { PasswordChangeRequiredPage } from "@/pages/password-change-required";
import { RegisterPage } from "@/pages/register";
import { WelcomePage } from "@/pages/welcome";

const AskEposPage = lazy(() => import("@/pages/ask-epos").then(module => ({ default: module.AskEposPage })));
const CalendarPage = lazy(() => import("@/pages/calendar").then(module => ({ default: module.CalendarPage })));
const ChangeRequestsPage = lazy(() => import("@/pages/change-requests").then(module => ({ default: module.ChangeRequestsPage })));
const DecisionsPage = lazy(() => import("@/pages/decisions").then(module => ({ default: module.DecisionsPage })));
const ReportPage = lazy(() => import("@/pages/report").then(module => ({ default: module.ReportPage })));
const HomePage = lazy(() => import("@/pages/home").then(module => ({ default: module.HomePage })));
const InboxPage = lazy(() => import("@/pages/inbox").then(module => ({ default: module.InboxPage })));
const MyWorkPage = lazy(() => import("@/pages/my-work").then(module => ({ default: module.MyWorkPage })));
const OnboardingPage = lazy(() => import("@/pages/onboarding").then(module => ({ default: module.OnboardingPage })));
const IssuesPage = lazy(() => import("@/pages/issues").then(module => ({ default: module.IssuesPage })));
const PeoplePage = lazy(() => import("@/pages/people").then(module => ({ default: module.PeoplePage })));
const PortfolioPage = lazy(() => import("@/pages/portfolio").then(module => ({ default: module.PortfolioPage })));
const ProjectCreatePage = lazy(() => import("@/pages/project-create").then(module => ({ default: module.ProjectCreatePage })));
const ProjectWorkspacePage = lazy(() => import("@/pages/project-workspace").then(module => ({ default: module.ProjectWorkspacePage })));
const ProjectsPage = lazy(() => import("@/pages/projects").then(module => ({ default: module.ProjectsPage })));
const RequirementsPage = lazy(() => import("@/pages/requirements").then(module => ({ default: module.RequirementsPage })));
const RisksPage = lazy(() => import("@/pages/risks").then(module => ({ default: module.RisksPage })));
const RolePermissionsPage = lazy(() => import("@/pages/role-permissions").then(module => ({ default: module.RolePermissionsPage })));
const ScenariosPage = lazy(() => import("@/pages/scenarios").then(module => ({ default: module.ScenariosPage })));

function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-4 h-40 w-full" />
      </div>
    );
  }
  if (status === "anonymous") {
    // After a sign-out the next person should not land on the previous person's page.
    return <Navigate to="/login" replace state={sessionEndedByReader() ? undefined : { from: `${location.pathname}${location.search}` }} />;
  }
  // The API admits nothing else while a temporary password is in use, so nothing else is shown.
  if (user?.password_change_required) return <PasswordChangeRequiredPage />;
  return <>{children}</>;
}

/**
 * Gate a route on a permission. The backend still enforces access; this only prevents a user
 * being shown a page that would fail for them.
 */
function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}): JSX.Element {
  const { can } = useAuth();
  if (!can(permission)) {
    return (
      <>
      <PageHeader title="Access restricted" description="This area is not available to your current role." />
      <Card>
        <EmptyState
          headingLevel={2}
          title="Not available to your role"
          description="Your role does not include access to this area. Ask a workspace administrator if your work needs it."
        />
      </Card>
      </>
    );
  }
  return <>{children}</>;
}

export function App(): JSX.Element {
  const { status } = useAuth();
  const signedIn = status === "authenticated";

  return (
    <RouteErrorBoundary>
    <SaveFeedback />
    <Suspense fallback={<div className="w-full p-6"><LoadingRegion label="Opening workspace"/><Skeleton className="mb-5 h-8 max-w-sm"/><SkeletonCards/></div>}>
    <Routes>
      {status === "anonymous" ? <Route path="/" element={<WelcomePage />} /> : null}
      <Route path="/login" element={signedIn ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/register" element={signedIn ? <Navigate to="/welcome" replace /> : <RegisterPage />} />
      <Route
        path="/welcome"
        element={
          <RequireAuth>
            <OnboardingPage />
          </RequireAuth>
        }
      />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        {status !== "anonymous" ? <Route index element={<HomePage />} /> : null}
        <Route path="account/role" element={<RolePermissionsPage />} />
        <Route path="my-work" element={<MyWorkPage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route
          path="portfolio"
          element={
            <RequirePermission permission="portfolio.read">
              <PortfolioPage />
            </RequirePermission>
          }
        />
        <Route path="projects" element={<ProjectsPage />} />
        <Route
          path="projects/new"
          element={
            <RequirePermission permission="project.create">
              <ProjectCreatePage />
            </RequirePermission>
          }
        />
        <Route path="projects/:projectId" element={<ProjectWorkspacePage />} />
        <Route path="risks" element={<RisksPage />} />
        <Route path="issues" element={<IssuesPage />} />
        <Route path="requirements" element={<RequirementsPage />} />
        <Route path="change-requests" element={<ChangeRequestsPage />} />
        <Route path="decisions" element={<DecisionsPage />} />
        <Route
          path="report"
          element={
            <RequirePermission permission="report.read">
              <ReportPage />
            </RequirePermission>
          }
        />
        <Route
          path="scenarios"
          element={
            <RequirePermission permission="scenario.run">
              <ScenariosPage />
            </RequirePermission>
          }
        />
        <Route
          path="ask"
          element={
            <RequirePermission permission="copilot.ask">
              <AskEposPage />
            </RequirePermission>
          }
        />
        <Route
          path="admin/users"
          element={
            <RequirePermission permission="user.manage">
              <PeoplePage />
            </RequirePermission>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
    </Suspense>
    </RouteErrorBoundary>
  );
}
