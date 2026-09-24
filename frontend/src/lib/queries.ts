import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ANALYSIS_REFRESH_INTERVAL_MS, NOTIFICATION_REFRESH_INTERVAL_MS, WORK_REFRESH_INTERVAL_MS } from "@/config";
import { ApiError, request, withQuery } from "@/lib/api";
import { REVIEW_PENDING } from "@/lib/task-state";
import type {
  Action,
  ActionCreateInput,
  ActionStatus,
  Assumption,
  AssumptionCreateInput,
  ActivityEvent,
  ChangeImpact,
  ChangeRequest,
  ChangeRequestCreateInput,
  CopilotAnswer,
  ConversationDetail,
  ConversationSummary,
  DatabaseStatus,
  Decision,
  Deliverable,
  Dependency,
  DependencyCreateInput,
  ExecutiveReport,
  Gate,
  GateCreateInput,
  GateCriterion,
  GateCriterionCreateInput,
  GateReadiness,
  GateReview,
  GateReviewOutcome,
  GateStatus,
  InboxNotification,
  Invitation,
  InvitationIssued,
  Issue,
  IssueCreateInput,
  MeetingNote,
  MeetingNoteExtraction,
  Milestone,
  NotificationSummary,
  PasswordReset,
  PortfolioDashboard,
  Project,
  ProjectDashboard,
  ProjectDelta,
  ProjectMember,
  ProjectUserOption,
  Requirement,
  RequirementCreateInput,
  ResourceAllocation,
  ResourceCreateInput,
  Risk,
  RiskCreateInput,
  RoleDescriptor,
  ScenarioResult,
  ScenarioSensitivity,
  SearchResults,
  ServiceHealth,
  SessionInfo,
  SupportedQuestion,
  Task,
  TaskCreateInput,
  TaskProgressEntry,
  TaskReviewDecision,
  TestCase,
  TestCaseCreateInput,
  TestResultStatus,
  TraceabilityMatrix,
  TraceLink,
  TraceTargetType,
  User,
  WorkPackage,
} from "@/types/api";

export const queryKeys = {
  portfolio: ["portfolio"] as const,
  projects: ["projects"] as const,
  projectDashboard: (id: string) => ["project-dashboard", id] as const,
  workPackages: (id: string) => ["work-packages", id] as const,
  deliverables: (id: string) => ["deliverables", id] as const,
  milestones: (id: string) => ["milestones", id] as const,
  gates: (id: string) => ["gates", id] as const,
  gateCriteria: (id: string) => ["gate-criteria", id] as const,
  gateReadiness: (id: string) => ["gate-readiness", id] as const,
  gateReviews: (id: string) => ["gate-reviews", id] as const,
  tasks: (id: string) => ["tasks", id] as const,
  taskProgress: (taskId: string) => ["task-progress", taskId] as const,
  risks: (id: string) => ["risks", id] as const,
  riskRegister: (id?: string) => ["risk-register", id ?? "all"] as const,
  issues: (id?: string) => ["issues", id ?? "all"] as const,
  actions: (id: string) => ["actions", id] as const,
  requirements: (id: string) => ["requirements", id] as const,
  changeRequests: (id?: string) => ["change-requests", id ?? "all"] as const,
  decisions: (id?: string) => ["decisions", id ?? "all"] as const,
  projectDelta: (id: string, days: number) => ["project-delta", id, days] as const,
  executiveReport: (days: number) => ["executive-report", days] as const,
  search: (query: string) => ["search", query] as const,
  meetingNotes: (id?: string) => ["meeting-notes", id ?? "all"] as const,
  meetingNoteExtraction: (id: string) => ["meeting-note-extraction", id] as const,
  changeImpact: (id: string) => ["change-impact", id] as const,
  traceability: (id?: string) => ["traceability", id ?? "all"] as const,
  dependencies: ["dependencies"] as const,
  resources: (id: string) => ["resources", id] as const,
  activity: (id?: string) => ["activity", id ?? "all"] as const,
  copilotQuestions: ["copilot-questions"] as const,
  conversations: ["copilot-conversations"] as const,
  conversation: (id: number | null) => ["copilot-conversation", id] as const,
  users: ["users"] as const,
  invitations: ["invitations"] as const,
  sessions: ["auth-sessions"] as const,
  serviceHealth: ["service-health"] as const,
  reviewQueue: ["review-queue"] as const,
  notifications: ["notifications"] as const,
  notificationList: (unreadOnly: boolean) => ["notifications", "list", unreadOnly] as const,
  notificationSummary: ["notifications", "summary"] as const,
  requirementRegister: (id: string) => ["requirement-register", id] as const,
  traceLinks: (id: string) => ["trace-links", id] as const,
  testCases: (id: string) => ["test-cases", id] as const,
};

export function usePortfolio() {
  return useQuery({
    queryKey: queryKeys.portfolio,
    queryFn: () => request<PortfolioDashboard>("/analytics/portfolio"),
    refetchInterval: ANALYSIS_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export type PortfolioViewFilters = Partial<Record<
  "project_id" | "health_band" | "confidence_band" | "domain" | "manager" | "phase" | "priority" | "alert_severity" | "forecast_after" | "forecast_before" | "needs_attention", string
>>;

export function usePortfolioView(filters: PortfolioViewFilters) {
  const active = Object.values(filters).some(Boolean);
  return useQuery({
    queryKey: active ? [...queryKeys.portfolio, "view", filters] : queryKeys.portfolio,
    queryFn: ({ signal }) => request<PortfolioDashboard>(withQuery("/analytics/portfolio", filters), { signal }),
  });
}

export function useAlerts(projectId?: string) {
  return useQuery({
    queryKey: ["alerts", projectId ?? "all"],
    queryFn: ({ signal }) => request<import("@/types/api").Alert[]>(withQuery("/analytics/alerts", { project_id: projectId }), { signal }),
  });
}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => request<Project[]>("/projects"),
  });
}

export function useProjectDashboard(projectId: string) {
  return useQuery({
    queryKey: queryKeys.projectDashboard(projectId),
    queryFn: () => request<ProjectDashboard>(`/analytics/projects/${projectId}`),
    enabled: Boolean(projectId),
    refetchInterval: ANALYSIS_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useMilestones(projectId: string) {
  return useQuery({
    queryKey: queryKeys.milestones(projectId),
    queryFn: () => request<Milestone[]>(`/projects/${projectId}/milestones`),
    enabled: Boolean(projectId),
  });
}

export function useGates(projectId: string) {
  return useQuery({
    queryKey: queryKeys.gates(projectId),
    queryFn: () => request<Gate[]>(`/projects/${projectId}/gates`),
    enabled: Boolean(projectId),
  });
}

export function useGateCriteria(gateId: string) {
  return useQuery({
    queryKey: queryKeys.gateCriteria(gateId),
    queryFn: () => request<GateCriterion[]>(`/gates/${gateId}/criteria`),
    enabled: Boolean(gateId),
  });
}

export function useGateReadiness(gateId: string) {
  return useQuery({
    queryKey: queryKeys.gateReadiness(gateId),
    queryFn: () => request<GateReadiness>(`/gates/${gateId}/readiness`),
    enabled: Boolean(gateId),
  });
}

export function useGateReviews(gateId: string) {
  return useQuery({
    queryKey: queryKeys.gateReviews(gateId),
    queryFn: () => request<GateReview[]>(`/gates/${gateId}/reviews`),
    enabled: Boolean(gateId),
  });
}

export function useWorkPackages(projectId: string) {
  return useQuery({
    queryKey: queryKeys.workPackages(projectId),
    queryFn: () => request<WorkPackage[]>(`/projects/${projectId}/work-packages`),
    enabled: Boolean(projectId),
  });
}

export function useDeliverables(projectId: string) {
  return useQuery({
    queryKey: queryKeys.deliverables(projectId),
    queryFn: () => request<Deliverable[]>(`/projects/${projectId}/deliverables`),
    enabled: Boolean(projectId),
  });
}

export function useTasks(projectId: string) {
  return useQuery({
    queryKey: queryKeys.tasks(projectId),
    queryFn: () => request<Task[]>(`/projects/${projectId}/tasks`),
    enabled: Boolean(projectId),
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useTaskRegister(projectId?: string, enabled = true) {
  return useQuery({
    queryKey: ["task-register", projectId ?? "all"],
    queryFn: ({ signal }) => request<Task[]>(withQuery("/tasks", { project_id: projectId }), { signal }),
    enabled,
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useTaskAssignees(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["project-assignees", projectId],
    queryFn: ({ signal }) => request<ProjectUserOption[]>(`/projects/${projectId}/assignees`, { signal }),
    enabled: enabled && Boolean(projectId),
    staleTime: 0,
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useProjectMembers(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["project-members", projectId],
    queryFn: ({ signal }) => request<ProjectMember[]>(`/projects/${projectId}/members`, { signal }),
    enabled: enabled && Boolean(projectId),
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
  });
}

export function useMemberCandidates(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["member-candidates", projectId],
    queryFn: ({ signal }) => request<ProjectUserOption[]>(`/projects/${projectId}/member-candidates`, { signal }),
    enabled: enabled && Boolean(projectId),
    staleTime: 0,
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

function refreshMembership(client: ReturnType<typeof useQueryClient>, projectId: string): void {
  for (const key of ["project-members", "project-assignees", "member-candidates", "project-people"]) {
    void client.invalidateQueries({ queryKey: [key, projectId] });
  }
  void client.invalidateQueries({ queryKey: ["activity"] });
}

export function useAddProjectMember(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { user_id: number; project_role: string }) =>
      request<ProjectMember>(`/projects/${projectId}/members`, { method: "POST", body: input }),
    onSuccess: () => refreshMembership(client, projectId),
  });
}

export function useUpdateProjectMember(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { userId: number; project_role: string }) =>
      request<ProjectMember>(`/projects/${projectId}/members/${input.userId}`, { method: "PATCH", body: { project_role: input.project_role } }),
    onSuccess: () => refreshMembership(client, projectId),
  });
}

export function useRemoveProjectMember(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) => request<void>(`/projects/${projectId}/members/${userId}`, { method: "DELETE" }),
    onSuccess: () => refreshMembership(client, projectId),
  });
}

export function useMilestoneRegister(projectId?: string) {
  return useQuery({
    queryKey: ["milestone-register", projectId ?? "all"],
    queryFn: ({ signal }) => request<Milestone[]>(withQuery("/milestones", { project_id: projectId }), { signal }),
  });
}

export function useActionRegister(projectId?: string, enabled = true) {
  return useQuery({
    queryKey: ["action-register", projectId ?? "all"],
    queryFn: ({ signal }) => request<Action[]>(withQuery("/actions", { project_id: projectId }), { signal }),
    enabled,
  });
}

/** Move an action through its lifecycle. The API decides which moves are allowed and records why. */
export function useTransitionAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ action, target, rationale }: { action: Action; target: ActionStatus; rationale: string }) =>
      request<Action>(`/actions/${encodeURIComponent(action.action_id)}/transition`, {
        method: "POST",
        body: { target_status: target, ...(rationale ? { rationale } : {}), row_version: action.row_version },
      }),
    onSuccess: (action) => {
      client.setQueriesData<Action[]>({ queryKey: ["action-register"] }, rows => rows?.map(row => row.action_id === action.action_id ? action : row));
      void client.invalidateQueries({ queryKey: queryKeys.actions(action.project_id) });
      invalidateProject(client, action.project_id);
    },
    onError: (error, { action }) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: ["action-register"] });
        void client.invalidateQueries({ queryKey: queryKeys.actions(action.project_id) });
      }
    },
  });
}

/** Link an action to a project member's account, or remove the link. The API checks the member. */
export function useAssignAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ action, ownerUserId }: { action: Action; ownerUserId: number | null }) =>
      request<Action>(`/actions/${encodeURIComponent(action.action_id)}`, {
        method: "PATCH",
        body: { owner_user_id: ownerUserId, row_version: action.row_version },
      }),
    onSuccess: (action) => {
      client.setQueriesData<Action[]>({ queryKey: ["action-register"] }, rows => rows?.map(row => row.action_id === action.action_id ? action : row));
      void client.invalidateQueries({ queryKey: queryKeys.actions(action.project_id) });
      invalidateProject(client, action.project_id);
    },
    onError: (error, { action }) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: ["action-register"] });
        void client.invalidateQueries({ queryKey: queryKeys.actions(action.project_id) });
      }
    },
  });
}

export function useRisks(projectId: string) {
  return useQuery({
    queryKey: queryKeys.risks(projectId),
    queryFn: () => request<Risk[]>(`/projects/${projectId}/risks`),
    enabled: Boolean(projectId),
  });
}

/** The register across every project the caller may see, or one project when narrowed. */
export function useRiskRegister(projectId?: string) {
  return useQuery({
    queryKey: queryKeys.riskRegister(projectId),
    queryFn: () => request<Risk[]>(withQuery("/risks", { project_id: projectId })),
  });
}

export function useIssues(projectId?: string) {
  return useQuery({
    queryKey: queryKeys.issues(projectId),
    queryFn: () => request<Issue[]>(withQuery("/issues", { project_id: projectId })),
  });
}

export function useAssumptions(projectId: string) {
  return useQuery({
    queryKey: ["assumptions", projectId],
    queryFn: ({ signal }) => request<Assumption[]>(withQuery("/assumptions", { project_id: projectId }), { signal }),
    enabled: Boolean(projectId),
  });
}

/** Assumptions across every project the reader can see, or one project when given. */
export function useAssumptionRegister(projectId?: string) {
  return useQuery({
    queryKey: ["assumptions", projectId ?? "all"],
    queryFn: ({ signal }) => request<Assumption[]>(withQuery("/assumptions", { project_id: projectId }), { signal }),
  });
}

export function useActions(projectId: string) {
  return useQuery({
    queryKey: queryKeys.actions(projectId),
    queryFn: () => request<Action[]>(`/projects/${projectId}/actions`),
    enabled: Boolean(projectId),
  });
}

export function useRequirements(projectId: string) {
  return useQuery({
    queryKey: queryKeys.requirements(projectId),
    queryFn: () => request<Requirement[]>(`/projects/${projectId}/requirements`),
    enabled: Boolean(projectId),
  });
}

/** Requirement records with their versions, as needed to edit one safely. */
export function useRequirementRegister(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.requirementRegister(projectId),
    queryFn: ({ signal }) => request<Requirement[]>(withQuery("/requirements", { project_id: projectId }), { signal }),
    enabled: enabled && Boolean(projectId),
  });
}

export function useCreateRequirement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: RequirementCreateInput) =>
      request<Requirement>("/requirements", { method: "POST", body: input }),
    onSuccess: (requirement) => refreshVerification(client, requirement.project_id),
  });
}

export function useUpdateRequirement(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ requirementId, patch }: {
      requirementId: string;
      patch: Partial<Omit<RequirementCreateInput, "project_id">> & { row_version: number };
    }) => request<Requirement>(`/requirements/${encodeURIComponent(requirementId)}`, { method: "PATCH", body: patch }),
    onSuccess: (requirement) => refreshVerification(client, requirement.project_id),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: queryKeys.requirementRegister(projectId) });
      }
    },
  });
}

export function useTraceLinks(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.traceLinks(projectId),
    queryFn: ({ signal }) => request<TraceLink[]>(withQuery("/trace-links", { project_id: projectId }), { signal }),
    enabled: enabled && Boolean(projectId),
  });
}

export function useCreateTraceLink() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { project_id: string; requirement_id: string; target_type: TraceTargetType; target_id: string }) =>
      request<TraceLink>("/trace-links", { method: "POST", body: input }),
    // A duplicate or unknown target usually means the lists are stale, so they reload either way.
    onSettled: (_link, _error, input) => refreshVerification(client, input.project_id),
  });
}

export function useDeleteTraceLink(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (link: TraceLink) =>
      request<void>(withQuery(`/trace-links/${encodeURIComponent(link.trace_link_id)}`, { row_version: link.row_version ?? undefined }), { method: "DELETE" }),
    onSettled: () => refreshVerification(client, projectId),
  });
}

export function useTestCases(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.testCases(projectId),
    queryFn: ({ signal }) => request<TestCase[]>(`/projects/${encodeURIComponent(projectId)}/test-cases`, { signal }),
    enabled: enabled && Boolean(projectId),
  });
}

/** Record a verification result. A pass needs evidence, and a new result never keeps the old one. */
export function useRecordTestResult(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ testCase, status, evidence }: { testCase: TestCase; status: TestResultStatus; evidence?: string }) =>
      request<TestCase>(`/test-cases/${encodeURIComponent(testCase.test_case_id)}`, {
        method: "PATCH",
        body: { status, row_version: testCase.row_version, ...(evidence ? { verification_evidence: evidence } : {}) },
      }),
    onSettled: () => refreshVerification(client, projectId),
  });
}

export function useChangeRequests(projectId?: string) {
  return useQuery({
    queryKey: queryKeys.changeRequests(projectId),
    queryFn: () => request<ChangeRequest[]>(withQuery("/change-requests", { project_id: projectId })),
  });
}

export function useChangeImpact(changeRequestId: string | null) {
  return useQuery({
    queryKey: queryKeys.changeImpact(changeRequestId ?? ""),
    queryFn: () => request<ChangeImpact>(`/change-requests/${changeRequestId}/impact`),
    enabled: Boolean(changeRequestId),
  });
}

export function useDecisions(projectId?: string) {
  return useQuery({
    queryKey: queryKeys.decisions(projectId),
    queryFn: () => request<Decision[]>(withQuery("/decisions", { project_id: projectId })),
  });
}

export function useProjectDelta(projectId: string, days: number) {
  return useQuery({
    queryKey: queryKeys.projectDelta(projectId, days),
    queryFn: () => request<ProjectDelta>(`/projects/${projectId}/delta?days=${days}`),
  });
}

export function useExecutiveReport(days: number) {
  return useQuery({
    queryKey: queryKeys.executiveReport(days),
    queryFn: () => request<ExecutiveReport>(`/analytics/executive-report?days=${days}`),
  });
}

export function useWorkspaceSearch(query: string) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: queryKeys.search(trimmed),
    queryFn: () => request<SearchResults>(withQuery("/search", { q: trimmed, limit: "20" })),
    enabled: trimmed.length >= 2,
    staleTime: 30_000,
  });
}

export function useMeetingNotes(projectId?: string) {
  return useQuery({
    queryKey: queryKeys.meetingNotes(projectId),
    queryFn: () =>
      request<MeetingNote[]>(withQuery("/meeting-notes", { project_id: projectId })),
  });
}

export function useMeetingNoteExtraction(noteId: string | null) {
  return useQuery({
    queryKey: queryKeys.meetingNoteExtraction(noteId ?? ""),
    queryFn: () => request<MeetingNoteExtraction>(`/meeting-notes/${noteId}/extraction`),
    enabled: Boolean(noteId),
  });
}

export function useCaptureMeetingNote(projectId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, unknown>) =>
      request<MeetingNote>("/meeting-notes", { method: "POST", body: input }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.meetingNotes(projectId) });
      void client.invalidateQueries({ queryKey: ["meeting-notes"] });
      void client.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

export function usePromoteProposal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, ...body }: { noteId: string } & Record<string, unknown>) =>
      request<Record<string, unknown>>(`/meeting-notes/${noteId}/promote`, { method: "POST", body }),
    onSuccess: async () => {
      for (const key of ["actions", "risks", "activity", "project-dashboard", "action-register", "risk-register"]) {
        void client.invalidateQueries({ queryKey: [key] });
      }
      void client.invalidateQueries({ queryKey: queryKeys.portfolio });
      await client.invalidateQueries({ queryKey: ["decisions"] });
    },
  });
}

export function useRecordDecisionOutcome() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      decisionId,
      outcome,
      rationale,
      rowVersion,
    }: {
      decisionId: string;
      outcome: string;
      rationale: string;
      rowVersion: number;
    }) =>
      request<Decision>(`/decisions/${decisionId}/outcome`, {
        method: "POST",
        body: { outcome, rationale, row_version: rowVersion },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["decisions"] });
      void client.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

export function useCreateDecision() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, unknown>) =>
      request<Decision>("/decisions", { method: "POST", body: input }),
    onSuccess: async () => {
      void client.invalidateQueries({ queryKey: ["activity"] });
      await client.invalidateQueries({ queryKey: ["decisions"] });
    },
  });
}

export function useTraceability(projectId?: string) {
  return useQuery({
    queryKey: queryKeys.traceability(projectId),
    queryFn: () =>
      request<TraceabilityMatrix>(withQuery("/analytics/traceability", { project_id: projectId })),
  });
}

export function useDependencies() {
  return useQuery({
    queryKey: queryKeys.dependencies,
    queryFn: () => request<Dependency[]>("/scenarios/dependencies"),
  });
}

export function useResources(projectId: string) {
  return useQuery({
    queryKey: queryKeys.resources(projectId),
    queryFn: () => request<ResourceAllocation[]>(`/projects/${projectId}/resources`),
    enabled: Boolean(projectId),
  });
}

export function useActivity(projectId?: string, limit = 25) {
  return useQuery({
    queryKey: [...queryKeys.activity(projectId), limit],
    queryFn: () => request<ActivityEvent[]>(withQuery("/activity", { project_id: projectId, limit })),
    // Loading older history keeps the changes already on screen until the longer list arrives,
    // but another project's history is never shown in place of this one's.
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1] === (projectId ?? "all") ? previous : undefined,
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useCopilotQuestions() {
  return useQuery({
    queryKey: queryKeys.copilotQuestions,
    queryFn: () => request<SupportedQuestion[]>("/copilot/questions"),
  });
}

export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: () => request<User[]>("/admin/users"),
    enabled,
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useRoles(enabled: boolean) {
  return useQuery({ queryKey: ["roles"], queryFn: () => request<RoleDescriptor[]>("/admin/roles"), enabled });
}

function refreshUsers(client: ReturnType<typeof useQueryClient>): void {
  for (const key of ["users", "project-members", "project-assignees", "member-candidates", "activity"]) {
    void client.invalidateQueries({ queryKey: [key] });
  }
}

export function useSetUserRole() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      request<User>(`/admin/users/${userId}/role`, { method: "PATCH", body: { role } }),
    onSuccess: (user) => {
      client.setQueryData<User[]>(queryKeys.users, rows => rows?.map(row => row.id === user.id ? user : row));
      refreshUsers(client);
    },
  });
}

export function useSetUserActive() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: number; isActive: boolean }) =>
      request<User>(`/admin/users/${userId}/active`, { method: "PATCH", body: { is_active: isActive } }),
    onSuccess: (user) => {
      client.setQueryData<User[]>(queryKeys.users, rows => rows?.map(row => row.id === user.id ? user : row));
      refreshUsers(client);
    },
  });
}

/** Issue a one-time temporary password. The result is shown once and never cached as a query. */
export function useResetUserPassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) =>
      request<PasswordReset>(`/admin/users/${userId}/reset-password`, { method: "POST" }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["activity"] }); },
  });
}

/** End every session of another account, for example after a lost device. */
export function useRevokeUserSessions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) =>
      request<void>(`/admin/users/${userId}/revoke-sessions`, { method: "POST" }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["activity"] }); },
  });
}

export function useInvitations(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.invitations,
    queryFn: ({ signal }) => request<Invitation[]>("/admin/invitations", { signal }),
    enabled,
  });
}

/** Invite one address with a role. The code is returned once and never cached as a query. */
export function useCreateInvitation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; role: string }) =>
      request<InvitationIssued>("/admin/invitations", { method: "POST", body: input }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.invitations });
      void client.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

export function useRevokeInvitation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: number) =>
      request<Invitation>(`/admin/invitations/${invitationId}/revoke`, { method: "POST" }),
    onSuccess: (invitation) => {
      client.setQueryData<Invitation[]>(queryKeys.invitations, rows => rows?.map(row => row.id === invitation.id ? invitation : row));
      void client.invalidateQueries({ queryKey: queryKeys.invitations });
      void client.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

/** Change the signed-in user's password. The API then ends every session, this one included. */
export function useChangePassword() {
  return useMutation({
    mutationFn: (input: { current_password: string; new_password: string }) =>
      request<void>("/auth/change-password", { method: "POST", body: input }),
  });
}

/** The signed-in account's live sessions, most recently used first. */
export function useSessions(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.sessions,
    queryFn: ({ signal }) => request<SessionInfo[]>("/auth/sessions", { signal }),
    enabled,
    staleTime: 0,
  });
}

export function useRevokeSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      request<void>(`/auth/sessions/${encodeURIComponent(sessionId)}/revoke`, { method: "POST" }),
    // A refusal usually means the list is stale, so it is reloaded either way.
    onSettled: () => { void client.invalidateQueries({ queryKey: queryKeys.sessions }); },
  });
}

export function useRevokeOtherSessions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<void>("/auth/sessions/revoke-others", { method: "POST" }),
    onSettled: () => { void client.invalidateQueries({ queryKey: queryKeys.sessions }); },
  });
}

/** Record that the project's status was reviewed today. The server supplies the date. */
export function useRecordStatusUpdate(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      // Nothing the user edited is sent, so the latest version is the right one to confirm.
      const current = await request<Project>(`/projects/${projectId}`);
      return request<Project>(`/projects/${projectId}/status-update`, {
        method: "POST",
        body: { row_version: current.row_version },
      });
    },
    onSuccess: () => {
      invalidateProject(client, projectId);
      void client.invalidateQueries({ queryKey: queryKeys.projects });
      void client.invalidateQueries({ queryKey: queryKeys.portfolio });
      void client.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

export function useServiceHealth() {
  return useQuery({
    queryKey: queryKeys.serviceHealth,
    queryFn: () => request<ServiceHealth>("/health"),
  });
}

/** The signed-in user's notifications, newest first. */
export function useNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: queryKeys.notificationList(unreadOnly),
    queryFn: ({ signal }) => request<InboxNotification[]>(withQuery("/notifications", { unread_only: String(unreadOnly) }), { signal }),
    refetchInterval: NOTIFICATION_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

/** The unread count. Polling pauses while the tab is hidden, React Query's default. */
export function useNotificationSummary(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.notificationSummary,
    queryFn: ({ signal }) => request<NotificationSummary>("/notifications/summary", { signal }),
    enabled,
    refetchInterval: NOTIFICATION_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useMarkNotificationRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: number) =>
      request<InboxNotification>(`/notifications/${notificationId}/read`, { method: "POST" }),
    onSuccess: (notification) => {
      client.setQueriesData<InboxNotification[]>(
        { queryKey: ["notifications", "list"] },
        rows => rows?.map(row => row.id === notification.id ? notification : row),
      );
      void client.invalidateQueries({ queryKey: queryKeys.notifications });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<NotificationSummary>("/notifications/read-all", { method: "POST" }),
    onSuccess: (summary) => {
      client.setQueryData<NotificationSummary>(queryKeys.notificationSummary, summary);
      void client.invalidateQueries({ queryKey: queryKeys.notifications });
    },
  });
}

export function useAskCopilot() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { question: string; project_id?: string; conversation_id?: number; reset_context?: boolean }) =>
      request<CopilotAnswer>("/copilot/ask", { method: "POST", body: input }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: queryKeys.conversations }); },
  });
}

export function useConversations() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: ({ signal }) => request<ConversationSummary[]>("/copilot/conversations", { signal }) });
}

export function useConversation(id: number | null) {
  return useQuery({ queryKey: queryKeys.conversation(id), enabled: id !== null, staleTime: 0,
    queryFn: ({ signal }) => request<ConversationDetail>(`/copilot/conversations/${id}`, { signal }) });
}

export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (id: number) => request<void>(`/copilot/conversations/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => { client.removeQueries({ queryKey: queryKeys.conversation(id) }); void client.invalidateQueries({ queryKey: queryKeys.conversations }); } });
}

export function useRunScenario() {
  return useMutation({
    mutationFn: (input: { dependency_id: string; additional_delay_days: number }) =>
      request<ScenarioResult>("/scenarios/dependency-delay", { method: "POST", body: input }),
  });
}

export function useRunScenarioSensitivity() {
  return useMutation({
    mutationFn: (input: {
      intervention_type: "dependency_delay";
      target_id: string;
      values?: number[];
    }) => request<ScenarioSensitivity>("/scenarios/sensitivity", { method: "POST", body: input }),
  });
}

export function useExplainScenario() {
  return useMutation({
    mutationFn: (input: { dependency_id: string; additional_delay_days: number }) =>
      request<CopilotAnswer>("/scenarios/explain", { method: "POST", body: input }),
  });
}

/** Invalidate everything derived from a project so scores refresh after an edit. */
function invalidateProject(client: ReturnType<typeof useQueryClient>, projectId: string): void {
  void client.invalidateQueries({ queryKey: queryKeys.projectDashboard(projectId) });
  void client.invalidateQueries({ queryKey: queryKeys.portfolio });
  void client.invalidateQueries({ queryKey: ["executive-report"] });
  void client.invalidateQueries({ queryKey: ["alerts"] });
  void client.invalidateQueries({ queryKey: ["task-register"] });
  void client.invalidateQueries({ queryKey: ["milestone-register"] });
  void client.invalidateQueries({ queryKey: ["action-register"] });
  void client.invalidateQueries({ queryKey: ["project-delta", projectId] });
  void client.invalidateQueries({ queryKey: ["search"] });
  void client.invalidateQueries({ queryKey: queryKeys.dependencies });
  void client.invalidateQueries({ queryKey: ["activity"] });
}

/** Requirement, trace-link and test-result writes change coverage and change impact. */
function refreshVerification(client: ReturnType<typeof useQueryClient>, projectId: string): void {
  void client.invalidateQueries({ queryKey: ["traceability"] });
  void client.invalidateQueries({ queryKey: ["change-impact"] });
  void client.invalidateQueries({ queryKey: queryKeys.requirementRegister(projectId) });
  void client.invalidateQueries({ queryKey: queryKeys.traceLinks(projectId) });
  void client.invalidateQueries({ queryKey: queryKeys.testCases(projectId) });
  invalidateProject(client, projectId);
}

export function useUpdateTask(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, patch }: { taskId: string; patch: Partial<Task> & { row_version: number; progress_note?: string } }) =>
      request<Task>(`/tasks/${taskId}`, { method: "PATCH", body: patch }),
    onSuccess: (task) => refreshTask(client, task),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
        void client.invalidateQueries({ queryKey: ["task-register"] });
      }
    },
  });
}

function refreshTask(client: ReturnType<typeof useQueryClient>, task: Task): void {
  client.setQueriesData<Task[]>({ queryKey: ["task-register"] }, rows => rows?.map(row => row.task_id === task.task_id ? task : row));
  client.setQueryData<Task[]>(queryKeys.tasks(task.project_id), rows => rows?.map(row => row.task_id === task.task_id ? task : row));
  void client.invalidateQueries({ queryKey: queryKeys.tasks(task.project_id) });
  void client.invalidateQueries({ queryKey: queryKeys.taskProgress(task.task_id) });
  invalidateProject(client, task.project_id);
}

/** Every recorded report on a task, newest first, with the notes their authors added. */
export function useTaskProgress(taskId: string) {
  return useQuery({
    queryKey: queryKeys.taskProgress(taskId),
    queryFn: () => request<TaskProgressEntry[]>(`/tasks/${taskId}/progress`),
  });
}

export function useCreateTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: TaskCreateInput) => request<Task>("/tasks", { method: "POST", body: input }),
    onSuccess: async (task) => {
      invalidateProject(client, task.project_id);
      await client.invalidateQueries({ queryKey: queryKeys.tasks(task.project_id) });
    },
  });
}

export function useCompleteTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ task, note }: { task: Task; note?: string }) =>
      request<Task>(`/tasks/${task.task_id}/complete`, {
        method: "POST",
        body: { row_version: task.row_version, ...(note ? { progress_note: note } : {}) },
      }),
    onSuccess: (task) => refreshTask(client, task),
    onError: (error, { task }) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: queryKeys.tasks(task.project_id) });
        void client.invalidateQueries({ queryKey: ["task-register"] });
      }
    },
  });
}

/** Tasks the signed-in manager can see whose reported completion is waiting for a decision. */
export function useReviewQueue() {
  return useQuery({
    queryKey: queryKeys.reviewQueue,
    queryFn: ({ signal }) => request<Task[]>(`/tasks?review_status=${encodeURIComponent(REVIEW_PENDING)}`, { signal }),
    refetchInterval: WORK_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

/** Accept reported completion, or return the task to its assignee with the reason. */
export function useReviewTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ task, decision, note }: { task: Task; decision: TaskReviewDecision; note?: string }) =>
      request<Task>(`/tasks/${encodeURIComponent(task.task_id)}/review`, {
        method: "POST",
        body: { decision, row_version: task.row_version, ...(note ? { note } : {}) },
      }),
    onSuccess: (task) => {
      client.setQueryData<Task[]>(queryKeys.reviewQueue, rows => rows?.filter(row => row.task_id !== task.task_id));
      refreshTask(client, task);
      void client.invalidateQueries({ queryKey: queryKeys.reviewQueue });
      void client.invalidateQueries({ queryKey: queryKeys.notifications });
    },
    onError: (error, { task }) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: queryKeys.tasks(task.project_id) });
        void client.invalidateQueries({ queryKey: ["task-register"] });
        void client.invalidateQueries({ queryKey: queryKeys.reviewQueue });
      }
    },
  });
}

export function useUpdateRisk(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ riskId, patch }: { riskId: string; patch: Partial<Risk> & { row_version: number; rationale?: string } }) =>
      request<Risk>(`/risks/${riskId}`, { method: "PATCH", body: patch }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.risks(projectId) });
      void client.invalidateQueries({ queryKey: ["risk-register"] });
      invalidateProject(client, projectId);
    },
  });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: Project & { project_manager_user_id?: number }) => request<Project>("/projects", { method: "POST", body: input }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.projects });
      void client.invalidateQueries({ queryKey: queryKeys.portfolio });
      void client.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

export function useCreateMilestone() {
  const client = useQueryClient();
  return useMutation({
    // Variance days are calculated by the API and an actual date rarely exists at creation.
    mutationFn: (
      input: Omit<Milestone, "milestone_id" | "row_version" | "actual_date" | "forecast_variance_days" | "actual_variance_days"> & {
        milestone_id?: string;
        actual_date?: string | null;
      },
    ) => request<Milestone>("/milestones", { method: "POST", body: input }),
    onSuccess: async (milestone) => {
      invalidateProject(client, milestone.project_id);
      await client.invalidateQueries({ queryKey: queryKeys.milestones(milestone.project_id) });
    },
  });
}

export function useCreateRisk() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: RiskCreateInput) =>
      request<Risk>("/risks", { method: "POST", body: input }),
    onSuccess: async (risk) => {
      invalidateProject(client, risk.project_id);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.risks(risk.project_id) }),
        client.invalidateQueries({ queryKey: ["risk-register"] }),
      ]);
    },
  });
}

export function useDecideChangeRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      changeRequestId,
      decision,
      rationale,
      rowVersion,
    }: {
      changeRequestId: string;
      decision: string;
      rationale: string;
      rowVersion: number;
    }) =>
      request<ChangeRequest>(`/change-requests/${changeRequestId}/decision`, {
        method: "POST",
        body: { decision, rationale, row_version: rowVersion },
      }),
    onSuccess: (changeRequest) => {
      void client.invalidateQueries({ queryKey: ["change-requests"] });
      invalidateProject(client, changeRequest.project_id);
    },
  });
}

/** A stale version means someone else changed the record, so its register is re-read. */
function refetchOnConflict(client: ReturnType<typeof useQueryClient>, error: unknown, key: readonly unknown[]): void {
  if (error instanceof ApiError && error.status === 409) void client.invalidateQueries({ queryKey: key });
}

export function useCreateIssue() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: IssueCreateInput) => request<Issue>("/issues", { method: "POST", body: input }),
    onSuccess: async (issue) => {
      invalidateProject(client, issue.project_id);
      await client.invalidateQueries({ queryKey: ["issues"] });
    },
  });
}

/** Move an issue through its lifecycle. Resolving records the reasoning as the resolution. */
export function useTransitionIssue() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ issue, target, rationale }: { issue: Issue; target: string; rationale: string }) =>
      request<Issue>(`/issues/${encodeURIComponent(issue.issue_id)}/transition`, {
        method: "POST",
        body: { target_status: target, ...(rationale ? { rationale } : {}), row_version: issue.row_version },
      }),
    onSuccess: (issue) => {
      void client.invalidateQueries({ queryKey: ["issues"] });
      invalidateProject(client, issue.project_id);
    },
    onError: (error) => refetchOnConflict(client, error, ["issues"]),
  });
}

export function useCreateAssumption() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: AssumptionCreateInput) =>
      request<Assumption>("/assumptions", { method: "POST", body: input }),
    onSuccess: async (assumption) => {
      invalidateProject(client, assumption.project_id);
      await client.invalidateQueries({ queryKey: ["assumptions"] });
    },
  });
}

/** Validate, invalidate, retire or reopen an assumption, with the evidence behind the call. */
export function useTransitionAssumption() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ assumption, target, evidence }: { assumption: Assumption; target: string; evidence: string }) =>
      request<Assumption>(`/assumptions/${encodeURIComponent(assumption.assumption_id)}/transition`, {
        method: "POST",
        body: { target_status: target, evidence, row_version: assumption.row_version },
      }),
    onSuccess: (assumption) => {
      void client.invalidateQueries({ queryKey: ["assumptions"] });
      invalidateProject(client, assumption.project_id);
    },
    onError: (error) => refetchOnConflict(client, error, ["assumptions"]),
  });
}

/** Raise a change request. The requester is always the signed-in account. */
export function useCreateChangeRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ChangeRequestCreateInput) =>
      request<ChangeRequest>("/change-requests", { method: "POST", body: input }),
    onSuccess: async (changeRequest) => {
      void client.invalidateQueries({ queryKey: ["traceability"] });
      invalidateProject(client, changeRequest.project_id);
      await client.invalidateQueries({ queryKey: ["change-requests"] });
    },
  });
}

function refreshGate(client: ReturnType<typeof useQueryClient>, projectId: string, gateId: string): void {
  void client.invalidateQueries({ queryKey: queryKeys.gates(projectId) });
  void client.invalidateQueries({ queryKey: queryKeys.gateReadiness(gateId) });
  void client.invalidateQueries({ queryKey: queryKeys.gateCriteria(gateId) });
  void client.invalidateQueries({ queryKey: queryKeys.gateReviews(gateId) });
  void client.invalidateQueries({ queryKey: ["activity"] });
}

export function useCreateGate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: GateCreateInput) => request<Gate>("/gates", { method: "POST", body: input }),
    onSuccess: async (gate) => {
      refreshGate(client, gate.project_id, gate.gate_id);
      await client.invalidateQueries({ queryKey: queryKeys.gates(gate.project_id) });
    },
  });
}

export function useTransitionGate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ gate, target, rationale }: { gate: Gate; target: GateStatus; rationale: string }) =>
      request<Gate>(`/gates/${encodeURIComponent(gate.gate_id)}/transition`, {
        method: "POST",
        body: { target_status: target, rationale, row_version: gate.row_version },
      }),
    onSuccess: (gate) => refreshGate(client, gate.project_id, gate.gate_id),
    onError: (error, { gate }) => refetchOnConflict(client, error, queryKeys.gates(gate.project_id)),
  });
}

export function useCreateGateCriterion(gate: Gate) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: GateCriterionCreateInput) =>
      request<GateCriterion>(`/gates/${encodeURIComponent(gate.gate_id)}/criteria`, { method: "POST", body: input }),
    onSuccess: () => refreshGate(client, gate.project_id, gate.gate_id),
  });
}

/** Record a criterion as met or not met. A met criterion that requires evidence must name it. */
export function useAssessGateCriterion(gate: Gate) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ criterion, target, rationale, evidence }: {
      criterion: GateCriterion; target: "Met" | "Not Met"; rationale: string; evidence?: string;
    }) =>
      request<GateCriterion>(
        `/gates/${encodeURIComponent(gate.gate_id)}/criteria/${encodeURIComponent(criterion.criterion_id)}/assessment`,
        {
          method: "POST",
          body: { target_status: target, rationale, row_version: criterion.row_version, ...(evidence ? { evidence_reference: evidence } : {}) },
        },
      ),
    onSuccess: () => refreshGate(client, gate.project_id, gate.gate_id),
    onError: (error) => refetchOnConflict(client, error, queryKeys.gateCriteria(gate.gate_id)),
  });
}

/** Append the immutable human review for the Gate's current review cycle. */
export function useRecordGateReview(gate: Gate) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { outcome: GateReviewOutcome; rationale: string; conditions: string | null }) =>
      request<GateReview>(`/gates/${encodeURIComponent(gate.gate_id)}/reviews`, { method: "POST", body: input }),
    onSuccess: () => refreshGate(client, gate.project_id, gate.gate_id),
  });
}

export function useCreateDependency() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: DependencyCreateInput) =>
      request<Dependency>("/dependencies", { method: "POST", body: input }),
    onSuccess: (dependency) => invalidateProject(client, dependency.project_id),
  });
}

export function useCreateAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ActionCreateInput) => request<Action>("/actions", { method: "POST", body: input }),
    onSuccess: async (action) => {
      invalidateProject(client, action.project_id);
      await client.invalidateQueries({ queryKey: queryKeys.actions(action.project_id) });
    },
  });
}

/** Define a test case. It starts Not Run; a result is recorded separately with its evidence. */
export function useCreateTestCase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: TestCaseCreateInput) =>
      request<TestCase>("/test-cases", { method: "POST", body: input }),
    onSuccess: (testCase) => refreshVerification(client, testCase.project_id),
  });
}

/** Record one person's allocated and available hours for a week. */
export function useCreateResource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ResourceCreateInput) =>
      request<ResourceAllocation>("/resources", { method: "POST", body: input }),
    onSuccess: (resource) => {
      void client.invalidateQueries({ queryKey: queryKeys.resources(resource.project_id) });
      invalidateProject(client, resource.project_id);
    },
  });
}

/** Amend a decision that is still proposed. Its outcome is recorded separately. */
export function useUpdateDecision() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ decision, patch }: { decision: Decision; patch: Record<string, unknown> }) =>
      request<Decision>(`/decisions/${encodeURIComponent(decision.decision_id)}`, {
        method: "PATCH",
        body: { ...patch, row_version: decision.row_version },
      }),
    onSuccess: async () => {
      void client.invalidateQueries({ queryKey: ["activity"] });
      await client.invalidateQueries({ queryKey: ["decisions"] });
    },
    onError: (error) => refetchOnConflict(client, error, ["decisions"]),
  });
}

/** Amend an issue's description, severity, owner, dates or the risk it came from. */
export function useUpdateIssue() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ issue, patch }: { issue: Issue; patch: Record<string, unknown> }) =>
      request<Issue>(`/issues/${encodeURIComponent(issue.issue_id)}`, {
        method: "PATCH",
        body: { ...patch, row_version: issue.row_version },
      }),
    onSuccess: async (issue) => {
      invalidateProject(client, issue.project_id);
      await client.invalidateQueries({ queryKey: ["issues"] });
    },
    onError: (error) => refetchOnConflict(client, error, ["issues"]),
  });
}

/** Amend an assumption's wording, owner, due date or consequence. */
export function useUpdateAssumption() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ assumption, patch }: { assumption: Assumption; patch: Record<string, unknown> }) =>
      request<Assumption>(`/assumptions/${encodeURIComponent(assumption.assumption_id)}`, {
        method: "PATCH",
        body: { ...patch, row_version: assumption.row_version },
      }),
    onSuccess: async (assumption) => {
      invalidateProject(client, assumption.project_id);
      await client.invalidateQueries({ queryKey: ["assumptions"] });
    },
    onError: (error) => refetchOnConflict(client, error, ["assumptions"]),
  });
}

/** The assignee accepts new work, or declines it with the reason. */
export function useRespondToAssignment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ task, decision, note }: { task: Task; decision: "accept" | "decline"; note?: string }) =>
      request<Task>(`/tasks/${encodeURIComponent(task.task_id)}/assignment`, {
        method: "POST",
        body: { decision, row_version: task.row_version, ...(note ? { note } : {}) },
      }),
    onSuccess: (task) => {
      refreshTask(client, task);
      void client.invalidateQueries({ queryKey: queryKeys.notifications });
    },
    onError: (error, { task }) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: ["task-register"] });
        void client.invalidateQueries({ queryKey: queryKeys.tasks(task.project_id) });
      }
    },
  });
}

/** Where the connected database stands against this release. Administrators only. */
export function useDatabaseStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["admin-database"],
    queryFn: ({ signal }) => request<DatabaseStatus>("/admin/database", { signal }),
    enabled,
  });
}

/** Apply the governed schema upgrades this release needs, without console access. */
export function useApplyDatabaseUpgrade() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<DatabaseStatus>("/admin/database/upgrade", { method: "POST" }),
    onSuccess: (status) => {
      client.setQueryData(["admin-database"], status);
      void client.invalidateQueries();
    },
  });
}

/** Withdraw a project and its records. The API keeps them for audit and refuses without the right. */
export function useDeleteProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (project: { project_id: string; row_version?: number | null }) =>
      request<void>(withQuery(`/projects/${encodeURIComponent(project.project_id)}`, { row_version: project.row_version ?? undefined }), { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries();
    },
  });
}
