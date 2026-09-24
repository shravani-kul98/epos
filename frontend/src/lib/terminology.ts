/**
 * User-facing vocabulary.
 *
 * The API already returns display labels for analysis factors. This map is the frontend's
 * guarantee that an internal key never reaches a user if a new one appears, and it is the single
 * place the approved wording is defined for the interface.
 */

const DISPLAY_NAMES: Record<string, string> = {
  task_execution: "Task Delivery",
  data_freshness: "Reporting Freshness",
  risk_exposure: "Risk Management",
  dependency_status: "Dependency Health",
  action_closure: "Action Follow-Through",
  resource_capacity: "Team Capacity",
  schedule_performance: "Schedule Health",
  milestone_readiness: "Milestone Readiness",
  data_completeness: "Information Completeness",
  ownership_coverage: "Accountability Coverage",
  source_reliability: "Data Availability",
};

/** Record types, as they should read in an evidence list. */
const RECORD_TYPES: Record<string, string> = {
  project: "Project",
  milestone: "Milestone",
  task: "Task",
  risk: "Risk",
  action: "Action",
  requirement: "Requirement",
  test_case: "Test case",
  trace_link: "Trace link",
  change_request: "Change request",
  changerequest: "Change request",
  meetingnote: "Meeting note",
  "meeting note": "Meeting note",
  workpackage: "Work package",
  testcase: "Test case",
  tracelink: "Trace link",
  gatecriterion: "Gate criterion",
  gatereview: "Gate review",
  dependency: "Dependency",
  resource: "Team capacity",
  alert: "Alert",
};

/** Turn any key or stored value into the approved user-facing term. */
export function displayTerm(value: string): string {
  const key = value.trim().toLowerCase();
  const mapped = DISPLAY_NAMES[key] ?? RECORD_TYPES[key];
  if (mapped) return mapped;
  if (!value.includes("_")) return value;
  const spaced = value.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function recordTypeLabel(recordType: string): string {
  return RECORD_TYPES[recordType.trim().toLowerCase()] ?? displayTerm(recordType);
}

/**
 * Plain-language description of what each role may do. Permission codes are deliberately not
 * shown; the user needs the capability, not the identifier behind it.
 */
export interface RoleGuide {
  label: string;
  summary: string;
  can: string[];
  cannot: string[];
}

export const ROLE_GUIDES: Record<string, RoleGuide> = {
  executive: {
    label: "Executive",
    summary: "Portfolio oversight, with read access across the workspace.",
    can: [
      "Review portfolio health and delivery confidence",
      "Read project detail, risks and milestones",
      "Open reports and ask EPOS about the portfolio",
    ],
    cannot: ["Edit project records", "Decide change requests", "Manage workspace members"],
  },
  engineer: {
    label: "Engineer",
    summary: "Delivery execution on the work assigned to you.",
    can: [
      "Update your tasks, progress and blockers",
      "Review project detail and requirements",
      "Ask EPOS about your work and your projects",
    ],
    cannot: [
      "Create projects",
      "Manage the risk register",
      "Decide change requests",
      "Manage workspace members",
    ],
  },
  engineering_lead: {
    label: "Engineering Lead",
    summary: "Team delivery, capacity and technical risk.",
    can: [
      "Manage tasks and milestones across your projects",
      "Maintain the risk register",
      "Run delivery scenarios and open reports",
    ],
    cannot: ["Create projects", "Decide change requests", "Manage workspace members"],
  },
  requirements_manager: {
    label: "Requirements Manager",
    summary: "Requirements, verification coverage and change control.",
    can: [
      "Maintain requirements and verification evidence",
      "Raise change requests",
      "Run delivery scenarios and open reports",
    ],
    cannot: ["Create projects", "Decide change requests", "Manage workspace members"],
  },
  project_manager: {
    label: "Project Manager",
    summary: "End-to-end delivery of the projects you own.",
    can: [
      "Create and manage projects",
      "Maintain milestones, tasks, risks and actions",
      "Raise and decide change requests",
      "Run delivery scenarios and open reports",
    ],
    cannot: ["Manage workspace members", "Change workspace settings"],
  },
  pmo_analyst: {
    label: "PMO Analyst",
    summary: "Portfolio control, exceptions and reporting quality.",
    can: [
      "Review every project in the portfolio",
      "Maintain risks and change decisions",
      "Run delivery scenarios and open reports",
    ],
    cannot: ["Manage workspace members", "Change workspace settings"],
  },
  administrator: {
    label: "Administrator",
    summary: "Full workspace access, including people and settings.",
    can: [
      "Everything a Project Manager can do",
      "Manage workspace members and their roles",
      "Change workspace settings",
    ],
    cannot: [],
  },
};

export function roleGuide(role: string): RoleGuide | undefined {
  return ROLE_GUIDES[role.trim().toLowerCase()];
}
