import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Bell, ChevronDown, ChevronRight, Inbox, Menu, Moon, Plus, Search, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { homeLabelFor } from "@/components/layout/navigation";
import { MagicButton } from "@/components/godui/magic-button";
import { StatusBadge, severityTone } from "@/components/ui/status-badge";
import { WORKSPACE_NAME } from "@/config";
import { useAuth } from "@/lib/auth";
import { formatDate, initials } from "@/lib/format";
import { useNotificationSummary } from "@/lib/queries";
import { useTheme } from "@/lib/theme";
import type { Alert, ProjectSummary } from "@/types/api";

const SEGMENT_LABELS: Record<string, string> = {
  portfolio: "Portfolio",
  projects: "Projects",
  "my-work": "My Work",
  inbox: "Inbox",
  calendar: "Calendar",
  risks: "Risks",
  issues: "Issues",
  requirements: "Requirements",
  "change-requests": "Change requests",
  decisions: "Decisions",
  report: "Executive report",
  scenarios: "Scenarios",
  ask: "Ask EPOS",
  admin: "Administration",
  users: "Team & Access",
  account: "Account",
  role: "Role and permissions",
  new: "New project",
};

/** Path segments that group pages but are not pages themselves, so their crumbs are not links. */
const UNROUTED_SEGMENTS = new Set(["account", "admin"]);
const PREVIEW_LIMIT = 6;
const SEVERITY_ORDER: Record<string, number> = { Critical: 0, High: 1 };

interface TopBarProps {
  onOpenCommandMenu: () => void;
  onOpenMobileNav: () => void;
  alerts: Alert[];
  projects?: ProjectSummary[];
  alertCount?: number;
  alertsLoading?: boolean;
}

export function TopBar({ onOpenCommandMenu, onOpenMobileNav, alerts, projects = [], alertCount, alertsLoading = false }: TopBarProps): JSX.Element {
  const { user, signOut, can, status } = useAuth();
  const { theme, toggle } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const inbox = useNotificationSummary(status === "authenticated");
  const unreadCount = inbox.data?.unread;
  const unread = typeof unreadCount === "number" ? unreadCount : undefined;
  const [openMenu, setOpenMenu] = useState<"none" | "alerts" | "account">("none");
  const containerRef = useRef<HTMLDivElement>(null);
  const alertTrigger = useRef<HTMLButtonElement>(null);
  const accountTrigger = useRef<HTMLButtonElement>(null);
  const alertPanelId = useId();
  const accountPanelId = useId();

  useEffect(() => {
    setOpenMenu("none");
  }, [location.pathname]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent): void {
      if (!containerRef.current?.contains(event.target as Node)) setOpenMenu("none");
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape" && openMenu !== "none") {
        setOpenMenu("none");
        (openMenu === "alerts" ? alertTrigger : accountTrigger).current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openMenu]);

  useEffect(() => {
    if (openMenu !== "none") containerRef.current?.querySelector<HTMLElement>('[data-topbar-panel] a, [data-topbar-panel] button')?.focus();
  }, [openMenu]);

  const segments = location.pathname.split("/").filter(Boolean);
  const crumbs = segments.length === 0 ? [homeLabelFor(can)] : segments.map((s) =>
    projects.find((project) => project.project_id === s)?.project_name ?? SEGMENT_LABELS[s] ?? s,
  );
  const urgent = alerts
    .filter((a) => a.severity === "Critical" || a.severity === "High")
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  const urgentCount = alertCount;
  const preview = urgent.slice(0, PREVIEW_LIMIT);
  const alertLabel = urgentCount !== undefined
    ? `Alerts, ${urgentCount} critical or high`
    : alertsLoading ? "Alerts, loading" : "Alerts, summary unavailable";

  return (
    <header
      data-print-hide
      className="workspace-topbar relative z-30 flex h-topbar shrink-0 items-center gap-1 border-b border-line bg-surface px-3 lg:gap-3 lg:px-5"
    >
      <Button
        variant="ghost"
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
        className="icon-button lg:hidden"
      >
        <Menu aria-hidden="true" className="h-4 w-4" />
      </Button>

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-1 text-body text-ink-secondary">
          {crumbs.map((crumb, index) => (
            <li key={`${crumb}-${index}`} className={index < crumbs.length - 1 ? "hidden min-w-0 items-center gap-1 sm:flex" : "flex min-w-0 items-center gap-1"}>
              {index > 0 ? (
                <ChevronRight aria-hidden="true" className="hidden h-3.5 w-3.5 shrink-0 text-ink-muted sm:block" />
              ) : null}
              {index < crumbs.length - 1 && !UNROUTED_SEGMENTS.has(segments[index] ?? "") ? (
                <Link to={`/${segments.slice(0, index + 1).join("/")}`} className="truncate hover:text-accent">{crumb}</Link>
              ) : index < crumbs.length - 1 ? <span className="truncate">{crumb}</span>
              : <span aria-current="page" title={crumb} className="truncate font-medium text-ink">{crumb}</span>}
            </li>
          ))}
        </ol>
      </nav>

      <Button
        variant="secondary"
        onClick={onOpenCommandMenu}
        aria-label="Search workspace"
        className="workspace-search-trigger flex h-10 items-center gap-2 rounded-control border border-line bg-surface-subtle px-2.5 text-meta text-ink-secondary hover:border-accent hover:text-ink"
      >
        <Search aria-hidden="true" className="h-3.5 w-3.5" />
        <span className="hidden md:inline">Search projects, tasks, risks</span>
        <kbd className="hidden rounded border border-line bg-surface px-1 text-meta lg:inline">Ctrl K</kbd>
      </Button>

      {can("project.create") ? (
        <MagicButton size="sm" aria-label="Create project" onClick={() => navigate("/projects/new")}>
          <Plus aria-hidden="true" className="h-4 w-4" />
          <span className="hidden sm:inline">Create project</span>
        </MagicButton>
      ) : null}

      <div ref={containerRef} className="flex items-center gap-1">
        <Button
          variant="ghost"
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="icon-button hidden sm:inline-flex"
        >
          {theme === "dark" ? (
            <Sun aria-hidden="true" className="h-4 w-4" />
          ) : (
            <Moon aria-hidden="true" className="h-4 w-4" />
          )}
        </Button>

        <Link to="/inbox" aria-label={unread === undefined ? "Inbox" : `Inbox, ${unread} unread`} className="icon-button relative">
          <Inbox aria-hidden="true" className="h-4 w-4" />
          {unread ? (
            <span
              aria-hidden="true"
              className="absolute right-0 top-0 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-meta font-medium text-ink-onaccent"
              data-numeric
            >
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </Link>

        <div className="relative">
          <Button
            ref={alertTrigger}
            variant="ghost"
            aria-label={alertLabel}
            aria-expanded={openMenu === "alerts"}
            aria-controls={openMenu === "alerts" ? alertPanelId : undefined}
            onClick={() => setOpenMenu((c) => (c === "alerts" ? "none" : "alerts"))}
            className="icon-button relative"
          >
            <Bell aria-hidden="true" className="h-4 w-4" />
            {urgentCount !== undefined && urgentCount > 0 ? (
              <span
                className="absolute right-0 top-0 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-critical px-1 text-meta font-medium text-ink-onstatus"
                data-numeric
              >
                {urgentCount}
              </span>
            ) : null}
          </Button>
          {openMenu === "alerts" ? (
            <div id={alertPanelId} data-topbar-panel role="region" aria-label="Alerts" className="workspace-menu-panel fixed right-4 top-topbar w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-card border border-line bg-surface shadow-overlay sm:absolute sm:right-0 sm:top-full sm:mt-2">
              <p className="border-b border-line px-3 py-2 text-meta font-semibold text-ink">
                {urgentCount === undefined
                  ? alertsLoading ? "Loading alerts" : "Alert summary unavailable"
                  : `Critical and high alerts · ${urgentCount} total${preview.length > 0 && preview.length < urgentCount ? ` · top ${preview.length} by severity` : ""}`}
              </p>
              {urgentCount === undefined ? (
                <p role="status" className="px-3 py-4 text-body text-ink-secondary">
                  {alertsLoading
                    ? "The portfolio summary is still loading."
                    : "The portfolio summary has not loaded or is unavailable. No alert count is inferred."}
                </p>
              ) : urgentCount === 0 ? (
                <p className="px-3 py-4 text-body text-ink-secondary">
                  No critical or high-severity alerts across the projects you can see.
                </p>
              ) : urgent.length === 0 ? (
                <p className="px-3 py-4 text-body text-ink-secondary">
                  The summary reports critical or high alerts, but no preview records are available.
                </p>
              ) : (
                <ul className="max-h-80 overflow-y-auto">
                  {preview.map((alert) => (
                    <li key={alert.alert_id} className="border-b border-line last:border-0">
                      <Link
                        to={`/projects/${alert.project_id}`}
                        className="block px-3 py-2.5 hover:bg-surface-subtle"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-meta font-medium text-ink-muted">
                            {projects.find((project) => project.project_id === alert.project_id)?.project_name ?? alert.project_id}
                          </span>
                          <StatusBadge label={alert.severity} tone={severityTone(alert.severity)} />
                        </div>
                        <p className="mt-1 text-body text-ink">{alert.title}</p>
                        <p className="mt-1 text-meta text-ink-muted">{alert.source_ids.join(" · ")}</p>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {urgentCount !== undefined && urgentCount > 0 && can("portfolio.read") ? (
                <Link to="/portfolio" className="block border-t border-line px-3 py-2 text-meta font-medium text-accent hover:bg-surface-subtle">
                  View all alerts in the portfolio
                </Link>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="relative">
          <Button
            ref={accountTrigger}
            variant="ghost"
            aria-label="Account menu"
            aria-expanded={openMenu === "account"}
            aria-controls={openMenu === "account" ? accountPanelId : undefined}
            onClick={() => setOpenMenu((c) => (c === "account" ? "none" : "account"))}
            className="workspace-account-trigger flex items-center gap-2 rounded-control py-1 pl-1 pr-2 hover:bg-surface-subtle"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-tint text-meta font-semibold text-accent">
              {user ? initials(user.full_name) : "?"}
            </span>
            <span className="hidden text-left leading-tight xl:block">
              <span className="block text-meta font-medium text-ink">{user?.full_name}</span>
              <span className="block text-meta text-ink-muted">{user?.role_label}</span>
            </span>
            <ChevronDown size={13} className="hidden text-ink-muted xl:block" aria-hidden="true" />
          </Button>
          {openMenu === "account" && user ? (
            <div id={accountPanelId} data-topbar-panel role="region" aria-label="Account" className="workspace-menu-panel fixed right-4 top-topbar w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-card border border-line bg-surface shadow-overlay sm:absolute sm:right-0 sm:top-full sm:mt-2">
              <div className="border-b border-line px-3 py-3">
                <p className="text-body font-medium text-ink">{user.full_name}</p>
                <p className="truncate text-meta text-ink-muted">{user.email}</p>
                <p className="mt-1.5 text-meta text-ink-secondary">{user.role_label}</p>
                <p className="text-meta text-ink-muted">{WORKSPACE_NAME}</p>
                {user.last_login_at ? (
                  <p className="mt-1 text-meta text-ink-muted">
                    Previous sign-in {formatDate(user.last_login_at)}
                  </p>
                ) : null}
              </div>
              <div className="p-1.5">
                <Link
                  to="/account/role"
                  className="block rounded-control px-2.5 py-2 text-body text-ink-secondary hover:bg-surface-subtle hover:text-ink"
                >
                  Role and permissions
                </Link>
                <Button
                  variant="ghost"
                  onClick={toggle}
                  className="w-full justify-start rounded-control px-2.5 py-2 text-left text-body text-ink-secondary hover:bg-surface-subtle hover:text-ink sm:hidden"
                >
                  {theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
                </Button>
                <Button
                  variant="ghost"
                  onClick={signOut}
                  className="w-full justify-start rounded-control px-2.5 py-2 text-left text-body text-ink-secondary hover:bg-surface-subtle hover:text-ink"
                >
                  Sign out
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
