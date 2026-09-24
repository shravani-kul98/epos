import { useQuery } from "@tanstack/react-query";

import { WORK_REFRESH_INTERVAL_MS } from "@/config";
import { request, withQuery } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ProjectUserOption } from "@/types/api";

export type RecordOwnerPurpose = "risk" | "decision" | "meeting" | "action" | "issue" | "assumption" | "requirement" | "gate";

export const RECORD_OWNER_PERMISSIONS: Record<RecordOwnerPurpose, string> = {
  risk: "risk.manage",
  decision: "change.create",
  meeting: "work.update",
  action: "action.manage",
  issue: "issue.manage",
  assumption: "assumption.manage",
  requirement: "requirement.manage",
  gate: "work.manage",
};

export interface ProjectCreateOptions {
  domains: string[];
  managers: ProjectUserOption[];
}

/** Active project members, including reviewers; deliberately not the task-assignee pool. */
export function useProjectPeople(projectId: string, purpose: RecordOwnerPurpose) {
  const { status, user, can } = useAuth();
  const canLoad = status === "authenticated" && can(RECORD_OWNER_PERMISSIONS[purpose]) && Boolean(projectId);
  const query = useQuery({
    queryKey: ["project-people", projectId, purpose, user?.id],
    queryFn: ({ signal }) => request<ProjectUserOption[]>(
      withQuery(`/projects/${encodeURIComponent(projectId)}/people`, { purpose }), { signal },
    ),
    enabled: canLoad,
    staleTime: 0,
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
  return { ...query, canLoad };
}

/** Authorized domains and active manager candidates are supplied by the server. */
export function useProjectCreateOptions() {
  const { status, user, can } = useAuth();
  const canLoad = status === "authenticated" && can("project.create");
  const query = useQuery({
    queryKey: ["project-create-options", user?.id],
    queryFn: ({ signal }) => request<ProjectCreateOptions>("/projects/options", { signal }),
    enabled: canLoad,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  return { ...query, canLoad };
}