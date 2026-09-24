let message: string | null = null;
const listeners = new Set<() => void>();

function publish(next: string | null): void {
  message = next;
  listeners.forEach(listener => listener());
}

export const saveFeedback = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
  snapshot: (): string | null => message,
  /** Show a specific confirmation, for flows that make several requests for one user action. */
  show(text: string): void {
    publish(text);
  },
  clear(): void {
    publish(null);
  },
};

const NAMES: Record<string, string> = {
  projects: "Project", tasks: "Task", milestones: "Milestone", risks: "Risk", issues: "Issue",
  actions: "Action", assumptions: "Assumption", requirements: "Requirement", decisions: "Decision",
  gates: "Gate", "change-requests": "Change request", "meeting-notes": "Meeting note",
  dependencies: "Dependency", "work-packages": "Work package", deliverables: "Deliverable",
  "test-cases": "Test case", resources: "Allocation", admin: "Account",
};

// Steps that are not plain saves, keyed by resource and the final path segment.
const STEPS: Record<string, string> = {
  "tasks/complete": "Task completion recorded.",
  "tasks/review": "Review recorded. The assignee has been told.",
  "tasks/assignment": "Your answer was sent to the project's managers.",
  "change-requests/decision": "Decision recorded against the change request.",
  "decisions/outcome": "Outcome recorded.",
  "gates/transition": "Gate moved to its next step.",
  "gates/reviews": "Gate review recorded.",
  "gates/criteria": "Criterion added.",
  "meeting-notes/promote": "Record created from the meeting note.",
  "issues/transition": "Issue moved to its next step.",
  "assumptions/transition": "Assumption moved to its next step.",
  "actions/transition": "Action moved to its next step.",
  "projects/status-update": "Status update recorded.",
};

export function announceSaved(method: string, path: string): void {
  if (!["POST", "PATCH", "DELETE"].includes(method)) return;
  const parts = path.split("?")[0]!.split("/").filter(Boolean);
  const resource = parts[0] ?? "";
  if (resource === "trace-links") {
    publish(method === "DELETE" ? "Link removed." : "Link added.");
    return;
  }
  const name = NAMES[resource];
  if (!name) return;
  if (parts.includes("members")) {
    publish("Project membership saved. Access changes take effect immediately.");
    return;
  }
  if (resource === "admin") {
    publish("Account access saved. The change is recorded in the audit trail.");
    return;
  }
  if (parts.length > 2) {
    const step = STEPS[`${resource}/${parts.at(-1)}`];
    if (step) publish(step);
    return;
  }
  const verb = method === "DELETE" ? "withdrawn" : method === "POST" && parts.length === 1 ? "created" : "saved";
  publish(`${name} ${verb}.`);
}
