import { Suspense, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { navigationFor } from "@/components/layout/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/topbar";
import { CommandMenu } from "@/components/ui/command-menu";
import { PageContext } from "@/components/ui/page-header";
import { LoadingRegion, SkeletonCards } from "@/components/ui/loading-skeleton";
import { WORKSPACE_NAME } from "@/config";
import { useAuth } from "@/lib/auth";
import { usePortfolio } from "@/lib/queries";

const COLLAPSE_KEY = "epos.nav.collapsed";
// Pages that read calculated scores, so the date the analysis is taken at matters to the reader.
const ANALYSIS_PAGES = [/^\/$/, /^\/portfolio/, /^\/projects$/, /^\/projects\/(?!new$)[^/]+$/, /^\/report/, /^\/scenarios/, /^\/ask/];

export function AppShell(): JSX.Element {
  const { can } = useAuth();
  const location = useLocation();
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === "true";
    } catch {
      return false;
    }
  });

  // The shell already needs the portfolio for notifications and search, and React Query shares
  // the single cached response with every page that follows.
  const portfolio = usePortfolio();

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSE_KEY, String(collapsed));
    } catch {
      // A blocked storage API only costs the remembered preference.
    }
  }, [collapsed]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const navigation = navigationFor(can);
  const projectId = location.pathname.match(/^\/projects\/([^/]+)$/)?.[1];
  const project = portfolio.data?.projects.find((item) => item.project_id === projectId);
  const analysisPage = ANALYSIS_PAGES.some((pattern) => pattern.test(location.pathname));

  useEffect(() => {
    setMobileNavOpen(false);
    const main = document.getElementById("main");
    main?.focus({ preventScroll: true });
    main?.scrollTo?.({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="workspace-shell flex h-dvh min-h-0">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Sidebar
        items={navigation}
        workspaceName={WORKSPACE_NAME}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((value) => !value)}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
        onOpenSearch={() => setCommandOpen(true)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          onOpenCommandMenu={() => setCommandOpen(true)}
          onOpenMobileNav={() => setMobileNavOpen(true)}
          alerts={portfolio.data?.top_alerts ?? []}
          projects={portfolio.data?.projects ?? []}
          alertCount={portfolio.data ? portfolio.data.alert_severities.critical + portfolio.data.alert_severities.high : undefined}
          alertsLoading={portfolio.isPending}
        />
        <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto focus-visible:ring-inset">
          <div className="mx-auto w-full max-w-content px-4 py-6 lg:px-6 lg:py-8">
            <PageContext.Provider value={{ scope: project?.project_name ?? (analysisPage ? "Portfolio workspace" : undefined), asOfDate: analysisPage ? portfolio.data?.as_of_date : undefined }}>
            <Suspense fallback={<><LoadingRegion label="Opening view"/><SkeletonCards/></>}>
            <Outlet />
            </Suspense>
            </PageContext.Provider>
          </div>
        </main>
      </div>
      <CommandMenu
        open={commandOpen}
        onClose={() => setCommandOpen(false)}
        navigation={navigation}
        projects={portfolio.data?.projects ?? []}
      />
    </div>
  );
}
