import type { LucideIcon } from "lucide-react";
import {
  CalendarDays,
  ChartNoAxesCombined,
  CircleAlert,
  FileCheck2,
  FileText,
  FolderKanban,
  Gavel,
  GitPullRequestArrow,
  Home,
  Inbox,
  ListChecks,
  MessageSquare,
  SlidersHorizontal,
  TriangleAlert,
  Users,
} from "lucide-react";

export interface NavigationItem {
  label: string;
  path: string;
  icon: LucideIcon;
  /** Permission required to see the entry. Undefined means every signed-in user sees it. */
  permission?: string;
  section: string;
  end?: boolean;
}

const ITEMS: NavigationItem[] = [
  { label: "Executive summary", path: "/", icon: Home, section: "Analysis", end: true },
  {
    label: "Portfolio",
    path: "/portfolio",
    icon: ChartNoAxesCombined,
    section: "Analysis",
    permission: "portfolio.read",
  },
  { label: "My Work", path: "/my-work", icon: ListChecks, section: "Execution" },
  { label: "Inbox", path: "/inbox", icon: Inbox, section: "Execution" },
  { label: "Calendar", path: "/calendar", icon: CalendarDays, section: "Execution" },
  {
    label: "Projects",
    path: "/projects",
    icon: FolderKanban,
    section: "Execution",
    permission: "portfolio.read",
  },
  {
    label: "Risks",
    path: "/risks",
    icon: CircleAlert,
    section: "Analysis",
    permission: "portfolio.read",
  },
  {
    label: "Issues",
    path: "/issues",
    icon: TriangleAlert,
    section: "Governance",
    permission: "portfolio.read",
  },
  {
    label: "Requirements",
    path: "/requirements",
    icon: FileCheck2,
    section: "Engineering",
    permission: "portfolio.read",
  },
  {
    label: "Change requests",
    path: "/change-requests",
    icon: GitPullRequestArrow,
    section: "Governance",
    permission: "portfolio.read",
  },
  {
    label: "Decisions",
    path: "/decisions",
    icon: Gavel,
    section: "Governance",
    permission: "portfolio.read",
  },
  {
    label: "Executive report",
    path: "/report",
    icon: FileText,
    section: "Analysis",
    permission: "report.read",
  },
  {
    label: "Scenarios",
    path: "/scenarios",
    icon: SlidersHorizontal,
    section: "Analysis",
    permission: "scenario.run",
  },
  {
    label: "Ask EPOS",
    path: "/ask",
    icon: MessageSquare,
    section: "Analysis",
    permission: "copilot.ask",
  },
  {
    label: "Team & Access",
    path: "/admin/users",
    icon: Users,
    section: "Administration",
    permission: "user.manage",
  },
];

/**
 * Navigation is filtered by permission so each role sees a coherent product rather than a menu
 * of dead ends. The backend remains the authority: hiding a link is presentation, not enforcement.
 */
export function navigationFor(can: (permission: string) => boolean): NavigationItem[] {
  return ITEMS.filter((item) => !item.permission || can(item.permission)).map((item) =>
    item.path === "/" ? { ...item, label: homeLabelFor(can) } : item,
  );
}

/** People without executive reporting land on their own overview, not an executive summary. */
export const HOME_LABEL_FOR_TEAM = "Overview";

/** The name of the start page for someone with these permissions. */
export function homeLabelFor(can: (permission: string) => boolean): string {
  return can("report.read") ? "Executive summary" : HOME_LABEL_FOR_TEAM;
}

export const NAVIGATION_SECTIONS = [
  "Analysis",
  "Execution",
  "Governance",
  "Engineering",
  "Administration",
];
