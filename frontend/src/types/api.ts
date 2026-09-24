/** Response contracts served by the EPOS API. Field names match the backend exactly. */

export type HealthBand = "Green" | "Amber" | "Red";
export type ConfidenceBand = "High" | "Medium" | "Low";
export type Severity = "Critical" | "High" | "Medium" | "Low";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  job_title: string | null;
  is_active: boolean;
  permissions: string[];
  created_at: string;
  last_login_at: string | null;
  /** Set after an administrator reset: the temporary password admits only choosing a new one. */
  password_change_required?: boolean;
}

export interface TokenResponse {
  access_token: string | null;
  token_type: string;
  expires_in_seconds: number;
  user: User;
  csrf_token?: string | null;
}

export interface SessionState {
  csrf_token: string;
  expires_at: string;
  session_expires_at: string;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string | null;
  current: boolean;
}

export interface Invitation {
  id: number;
  email: string;
  role: string;
  role_label: string;
  created_by: string;
  created_at: string;
  expires_at: string;
  status: "Pending" | "Accepted" | "Revoked" | "Expired";
}

export interface InvitationIssued {
  invitation: Invitation;
  code: string;
}

export interface PasswordReset {
  user_id: number;
  temporary_password: string;
}

export interface RoleDescriptor {
  role: string;
  label: string;
  permissions: string[];
}

export interface ProjectUserOption {
  user_id: number;
  full_name: string;
  email: string;
  workspace_role: string;
  role_label: string;
}

export interface ProjectMember {
  user_id: number;
  full_name: string;
  email: string;
  workspace_role: string;
  project_role: string;
  is_active: boolean;
  created_at: string;
}

export interface TaskCreateInput {
  project_id: string;
  milestone_id: string;
  task_name: string;
  owner_user_id: number | null;
  planned_end_date: string;
  forecast_end_date: string;
  status: string;
  completion_percent: number;
  review_required?: boolean;
}

export interface FactorBreakdown {
  key: string;
  label: string;
  description: string;
  score: number;
  weight: number;
  weighted_contribution: number;
  explanations: string[];
}

export interface Driver {
  factor_label: string;
  severity: Severity;
  message: string;
  source_ids: string[];
  score_impact_description: string;
}

export interface DataQualityIssue {
  issue_type: string;
  severity: Severity;
  message: string;
  source_ids: string[];
  remediation_hint: string;
}

export interface HealthResult {
  project_id: string;
  score: number;
  band: HealthBand;
  factors: FactorBreakdown[];
  critical_drivers: Driver[];
  source_ids: string[];
  as_of_date: string;
  calculated_at: string;
  assumptions_or_limitations: string[];
}

export interface ConfidenceResult {
  project_id: string;
  score: number;
  band: ConfidenceBand;
  factors: FactorBreakdown[];
  data_quality_issues: DataQualityIssue[];
  source_ids: string[];
  as_of_date: string;
  calculated_at: string;
  assumptions_or_limitations: string[];
}

export interface Alert {
  alert_id: string;
  project_id: string;
  severity: Severity;
  alert_type: string;
  alert_type_label: string;
  title: string;
  explanation: string;
  source_ids: string[];
  recommended_next_step: string;
  as_of_date: string;
  detected_at: string;
}

export interface ProjectSummary {
  assessment?: ProjectAssessment;
  project_id: string;
  project_name: string;
  domain: string;
  project_manager: string;
  project_phase: string;
  business_priority: string;
  forecast_end_date: string | null;
  health_score: number;
  health_band: HealthBand;
  confidence_score: number;
  confidence_band: ConfidenceBand;
  open_alert_count: number;
  critical_alert_count: number;
  /** Amber or red health, or a critical or high alert. Calculated by the API. */
  needs_attention?: boolean;
}

export interface BandCounts {
  green: number;
  amber: number;
  red: number;
}

export interface ConfidenceBandCounts {
  high: number;
  medium: number;
  low: number;
}

export interface SeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface PortfolioDashboard {
  as_of_date: string;
  project_count: number;
  unassessed_count?: number;
  health_bands: BandCounts;
  confidence_bands: ConfidenceBandCounts;
  alert_severities: SeverityCounts;
  project_phases: Record<string, number>;
  project_domains: Record<string, number>;
  projects: ProjectSummary[];
  top_alerts: Alert[];
}

export interface Project {
  row_version?: number | null;
  project_id: string;
  project_name: string;
  domain: string;
  project_manager: string;
  start_date: string;
  baseline_end_date: string | null;
  forecast_end_date: string | null;
  status_update_date: string | null;
  project_phase: string;
  business_priority: string;
}

export interface ProjectAssessment {
  is_assessed: boolean;
  reason: string;
  source_ids: string[];
}

export interface ProjectDashboard {
  assessment?: ProjectAssessment;
  project: Project;
  health: HealthResult;
  confidence: ConfidenceResult;
  alerts: Alert[];
}

export interface Milestone {
  row_version?: number | null;
  milestone_id: string;
  project_id: string;
  milestone_name: string;
  baseline_date: string | null;
  forecast_date: string | null;
  actual_date: string | null;
  forecast_variance_days: number | null;
  actual_variance_days: number | null;
  status: string;
  criticality: string;
  owner: string | null;
}

export type GateStatus =
  | "Not Started"
  | "Preparing"
  | "Ready for Review"
  | "In Review"
  | "Passed"
  | "Passed with Conditions"
  | "Failed"
  | "Deferred"
  | "Withdrawn";

export type GateReviewOutcome =
  | "Approved"
  | "Approved with Conditions"
  | "Rejected"
  | "Deferred";

export interface Gate {
  row_version?: number | null;
  gate_id: string;
  project_id: string;
  milestone_id: string | null;
  gate_name: string;
  sequence: number;
  planned_review_date: string;
  actual_review_date: string | null;
  owner: string;
  status: GateStatus;
  review_cycle: number;
  result: "Passed" | "Passed with Conditions" | "Failed" | "Deferred" | null;
  applicable_baseline: string | null;
}

export interface GateCriterion {
  row_version?: number | null;
  criterion_id: string;
  gate_id: string;
  project_id: string;
  criterion_type: "Entry" | "Exit";
  criterion_name: string;
  description: string;
  is_mandatory: boolean;
  evidence_required: boolean;
  status: "Not Assessed" | "Met" | "Not Met";
  evidence_reference: string | null;
  assessment_rationale: string | null;
  assessed_by: string | null;
  assessed_at: string | null;
}

export interface GateReview {
  review_id: string;
  gate_id: string;
  project_id: string;
  reviewer: string;
  review_cycle: number;
  outcome: GateReviewOutcome;
  rationale: string;
  conditions: string | null;
  reviewed_at: string;
  created_by: string;
}

export interface GateReadinessFinding {
  message: string;
  source_ids: string[];
}

export interface GateReadiness {
  gate_id: string;
  project_id: string;
  state: "Not Ready" | "Ready for Review" | "Approved" | "Approved with Conditions";
  percentage: number | null;
  complete_criterion_ids: string[];
  incomplete_criterion_ids: string[];
  blockers: GateReadinessFinding[];
  warnings: GateReadinessFinding[];
  evidence_references: string[];
  latest_review_id: string | null;
  latest_review_outcome: GateReviewOutcome | null;
  calculated_at: string;
  methodology_version: string;
  applicable_baseline: string | null;
}

export interface WorkPackage {
  row_version?: number | null;
  work_package_id: string;
  project_id: string;
  work_package_name: string;
  description: string;
  owner: string | null;
  accountable_owner: string | null;
  status: string;
  priority: string;
}

export interface Deliverable {
  row_version?: number | null;
  deliverable_id: string;
  project_id: string;
  work_package_id: string;
  deliverable_name: string;
  description: string;
  owner: string | null;
  accountable_owner: string | null;
  status: string;
  priority: string;
  acceptance_criteria: string | null;
  completion_evidence: string | null;
}

export type TaskReviewStatus = "Pending review" | "Accepted" | "Returned";
export type TaskReviewDecision = "accept" | "return";

export interface Task {
  row_version?: number | null;
  task_id: string;
  project_id: string;
  milestone_id: string;
  deliverable_id: string | null;
  parent_task_id: string | null;
  task_name: string;
  owner: string | null;
  owner_user_id: number | null;
  status: string;
  planned_start_date: string | null;
  forecast_start_date: string | null;
  actual_start_date: string | null;
  planned_end_date: string;
  forecast_end_date: string;
  actual_end_date: string | null;
  forecast_start_variance_days: number | null;
  forecast_finish_variance_days: number;
  actual_start_variance_days: number | null;
  actual_finish_variance_days: number | null;
  completion_percent: number;
  is_blocked: boolean;
  last_updated_date: string | null;
  review_required: boolean;
  review_status: TaskReviewStatus | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  /** Pending until the assignee accepts; Declined returns the work to its managers. */
  assignment_status?: "Pending" | "Accepted" | "Declined" | null;
  assignment_responded_at?: string | null;
  assignment_note?: string | null;
}

export interface Risk {
  row_version?: number | null;
  risk_id: string;
  project_id: string;
  risk_name: string;
  probability: number;
  impact: number;
  severity_score: number;
  status: string;
  mitigation_owner: string | null;
  mitigation_owner_user_id?: number | null;
  mitigation_status: string | null;
  due_date: string;
}

export type ActionStatus = "Open" | "In Progress" | "Blocked" | "Complete" | "Cancelled";

export interface Action {
  row_version?: number | null;
  action_id: string;
  project_id: string;
  action_description: string;
  owner: string | null;
  owner_user_id: number | null;
  due_date: string;
  status: string;
  priority: string;
  source_reference: string | null;
}

export interface Issue {
  row_version?: number | null;
  issue_id: string;
  project_id: string;
  title: string;
  description: string;
  severity: Severity;
  owner: string | null;
  owner_user_id?: number | null;
  status: string;
  raised_date: string;
  target_resolution_date: string | null;
  resolution_summary: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  source_reference: string | null;
}

export interface Assumption {
  row_version?: number | null;
  assumption_id: string;
  project_id: string;
  assumption_text: string;
  owner: string;
  owner_user_id?: number | null;
  status: string;
  validation_due_date: string | null;
  impact_if_false: string | null;
  validation_evidence: string | null;
  validated_by: string | null;
  validated_at: string | null;
  source_reference: string | null;
}

export interface Requirement {
  row_version?: number | null;
  requirement_id: string;
  project_id: string;
  requirement_text: string;
  requirement_type: string;
  priority: string;
  status: string;
  owner: string | null;
  last_updated_date: string | null;
}

export interface RequirementCreateInput {
  project_id: string;
  requirement_text: string;
  requirement_type: string;
  priority: string;
  status: string;
  owner?: string | null;
}

export type TestResultStatus = "Passed" | "Failed" | "Not Run";

export interface TestCase {
  row_version?: number | null;
  test_case_id: string;
  project_id: string;
  test_case_name: string;
  status: string;
  owner: string | null;
  verification_evidence: string | null;
  last_updated_date: string | null;
}

export type TraceTargetType = "Task" | "TestCase" | "Milestone";

export interface TraceLink {
  row_version?: number | null;
  trace_link_id: string;
  project_id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  link_type: string;
}

export interface InboxNotification {
  id: number;
  kind: string;
  title: string;
  detail: string | null;
  project_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  actor_name: string | null;
  created_at: string;
  read_at: string | null;
}

export interface NotificationSummary {
  unread: number;
}

export interface ChangeRequest {
  row_version?: number | null;
  change_request_id: string;
  project_id: string;
  requirement_id: string;
  change_description: string;
  reason: string;
  priority: string;
  status: string;
  requested_by: string | null;
  requested_date: string;
}

export interface MeetingNote {
  row_version?: number | null;
  note_id: string;
  project_id: string;
  title: string;
  meeting_date: string;
  attendees: string | null;
  body: string;
}

export interface MeetingNoteProposal {
  proposal_id: string;
  kind: "action" | "risk" | "decision";
  text: string;
  source_line_number: number;
  source_line: string;
  matched_phrase: string;
  suggested_owner: string | null;
  suggested_due_date: string | null;
}

export interface MeetingNoteExtraction {
  note_id: string;
  project_id: string;
  line_count: number;
  proposals: MeetingNoteProposal[];
  action_count: number;
  risk_count: number;
  decision_count: number;
}

export interface SearchHit {
  record_type: string;
  record_type_label: string;
  record_id: string;
  title: string;
  subtitle: string | null;
  status: string | null;
  project_id: string;
  project_name: string;
  path: string;
}

export interface SearchResults {
  query: string;
  total: number;
  hits: SearchHit[];
}

export interface ExecutiveReportItem {
  text: string;
  source_ids: string[];
}

export interface ExecutiveReportSection {
  key: string;
  title: string;
  summary: string;
  items: ExecutiveReportItem[];
}

export interface ExecutiveReport {
  as_of_date: string;
  window_days: number;
  generated_at: string;
  headline: string;
  project_count: number;
  health_bands: { green: number; amber: number; red: number };
  confidence_bands: { high: number; medium: number; low: number };
  alert_severities: { critical: number; high: number; medium: number; low: number };
  sections: ExecutiveReportSection[];
  source_ids: string[];
}

export interface ProjectDeltaEntry {
  entity_type: string;
  entity_id: string;
  change_type: "added" | "updated" | "withdrawn";
  headline: string;
  status: string | null;
  occurred_at: string;
  actor_name: string | null;
}

export interface ProjectDeltaGroup {
  key: string;
  label: string;
  added: number;
  updated: number;
  withdrawn: number;
  entries: ProjectDeltaEntry[];
}

export interface ProjectDelta {
  project_id: string;
  project_name: string;
  since: string;
  generated_at: string;
  total_changes: number;
  has_history: boolean;
  earliest_record_at: string | null;
  groups: ProjectDeltaGroup[];
}

export interface Decision {
  row_version?: number | null;
  decision_id: string;
  project_id: string;
  title: string;
  description: string;
  category: string;
  decision_date: string;
  owner: string;
  status: string;
  rationale: string | null;
  delivery_impact: string | null;
  related_milestone_id: string | null;
  related_risk_id: string | null;
  related_change_request_id: string | null;
  related_requirement_id: string | null;
  approver: string | null;
  approval_date: string | null;
  notes: string | null;
}

export interface ChangeImpact {
  change_request_id: string;
  requirement_id: string;
  affected_task_ids: string[];
  affected_test_case_ids: string[];
  affected_dependency_ids: string[];
  affected_milestone_ids: string[];
  estimated_schedule_impact_days: number;
  risk_level: Severity;
  explanation: string;
  source_ids: string[];
  as_of_date: string;
  calculated_at: string;
  assumptions_or_limitations: string[];
  evidence_status: "Assessed" | "Insufficient evidence";
}

export interface TraceabilityRow {
  requirement_id: string;
  requirement_text: string;
  project_id: string;
  requirement_status: string;
  priority: string;
  owner: string | null;
  linked_test_case_ids: string[];
  verified_test_case_ids: string[];
  trace_status: string;
  open_change_request_ids: string[];
}

export interface TraceabilityMatrix {
  as_of_date: string;
  project_id: string | null;
  total_requirements: number;
  status_counts: Record<string, number>;
  coverage_percent: number;
  rows: TraceabilityRow[];
}

export interface Dependency {
  row_version?: number | null;
  dependency_id: string;
  project_id: string;
  predecessor_type: string;
  predecessor_id: string;
  successor_type: string;
  successor_id: string;
  dependency_name: string;
  relationship_type:
    | "Finish-to-Start"
    | "Start-to-Start"
    | "Finish-to-Finish"
    | "Start-to-Finish"
    | null;
  lag_days: number | null;
  schedule_data_complete: boolean;
  status: string;
  delay_days: number;
  criticality: string;
}

export interface ResourceAllocation {
  resource_id: string;
  resource_name: string;
  project_id: string;
  allocated_hours: number;
  capacity_hours: number;
  utilisation_percent: number;
  is_overallocated: boolean;
  week_start_date: string;
  row_version?: number | null;
}

export interface ScenarioFactorDelta {
  factor: string;
  factor_label: string;
  baseline_score: number;
  scenario_score: number;
  score_delta: number;
  weight: number;
  weighted_contribution: number;
}

export interface ScheduleMovement {
  record_type: string;
  record_id: string;
  record_name: string;
  original_date: string;
  scenario_date: string;
  shift_days: number;
  controlling_dependency_id: string | null;
  controlling_predecessor_id: string | null;
  propagation_hop: number;
}

export interface ScenarioIntervention {
  intervention_type: string;
  target_id: string;
  value: number;
  unit: string;
  note: string | null;
}

export interface ScenarioComparison {
  project_id: string;
  project_name: string;
  baseline_health_score: number;
  baseline_health_band: HealthBand;
  scenario_health_score: number;
  scenario_health_band: HealthBand;
  health_score_delta: number;
  baseline_confidence_score: number;
  baseline_confidence_band: ConfidenceBand;
  scenario_confidence_score: number;
  scenario_confidence_band: ConfidenceBand;
  confidence_score_delta: number;
  baseline_alert_counts: SeverityCounts;
  scenario_alert_counts: SeverityCounts;
  new_alert_ids: string[];
  resolved_alert_ids: string[];
  changed_alert_ids: string[];
  baseline_forecast_end_date: string | null;
  scenario_forecast_end_date: string | null;
  forecast_end_shift_days: number;
  factor_deltas: ScenarioFactorDelta[];
}

export interface ScenarioResult {
  scenario_type: string;
  dependency_id: string;
  dependency_name: string;
  additional_delay_days: number;
  baseline_delay_days: number;
  scenario_delay_days: number;
  affected_projects: ScenarioComparison[];
  explanation: string;
  source_ids: string[];
  as_of_date: string;
  calculated_at: string;
  assumptions_or_limitations: string[];
  interventions: ScenarioIntervention[];
  schedule_movements: ScheduleMovement[];
  calculation_version: string;
  decision_brief?: Array<{
    kind: "schedule" | "score" | "coverage" | "review";
    headline: string;
    detail: string;
    project_id: string | null;
    source_ids: string[];
  }>;
}

export interface ScenarioThreshold {
  outcome: string;
  occurs_at_value: number | null;
  unit: string;
  tested_values: number[];
  explanation: string;
}

export interface ScenarioSensitivity {
  intervention_type: string;
  target_id: string;
  project_id: string;
  unit: string;
  tested_values: number[];
  health_scores: number[];
  forecast_shift_days: number[];
  is_responsive: boolean;
  saturated_at_value: number | null;
  thresholds: ScenarioThreshold[];
  assumptions_or_limitations: string[];
}

export interface ActivityEvent {
  id: number;
  occurred_at: string;
  action: string;
  entity_type: string;
  entity_id: string;
  project_id: string | null;
  summary: string;
  detail: string | null;
  changes?: ActivityFieldChange[] | null;
  actor_name: string | null;
  headline: string;
}

export interface ActivityFieldChange {
  field: string;
  label: string;
  before: unknown;
  after: unknown;
}

export interface TaskProgressEntry {
  id: number;
  occurred_at: string;
  action: string;
  actor_name: string | null;
  note: string | null;
  changes: ActivityFieldChange[];
}

export interface EvidenceRecord {
  record_type: string;
  record_id: string;
  fields: Record<string, string>;
}

export interface AppliedFilter {
  field: string;
  label: string;
  values: string[];
  excluded: boolean;
  interpreted_from: string | null;
}

export interface CopilotAnswer {
  status: "ok" | "unavailable" | "error" | "invalid_response" | "clarification";
  matched_intent: string | null;
  matched_question: string | null;
  executive_summary: string;
  key_findings: string[];
  recommended_actions: string[];
  source_ids: string[];
  human_review_required: boolean;
  disclaimer: string;
  warnings: string[];
  evidence: EvidenceRecord[];
  suggested_questions: string[];
  conversation_id: number | null;
  context?: Record<string, string>;
  project_references?: Array<{ project_id: string; project_name: string }>;
  applied_filters?: AppliedFilter[];
  unapplied_filters?: string[];
}

export interface ConversationSummary {
  id: number;
  title: string;
  project_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Omit<ConversationSummary, "message_count"> {
  context: Record<string, string>;
  messages: Array<{
    id: number;
    role: string;
    content: string;
    matched_intent: string | null;
    status: string | null;
    source_ids: string[];
    evidence: EvidenceRecord[];
    created_at: string;
    answer: CopilotAnswer | null;
  }>;
}

export interface SupportedQuestion {
  intent: string;
  question: string;
  requires_context: string | null;
}

export interface ServiceHealth {
  status: string;
  database_seeded: boolean;
  project_count: number;
  ai_configured: boolean;
  analysis_date: string;
}

/** Where the database stands against this release. Never carries a host or credential. */
export interface DatabaseStatus {
  dialect: string;
  current_revision: string | null;
  expected_revision: string | null;
  is_current: boolean;
  can_upgrade: boolean;
  automatic_upgrades: boolean;
  pending: { revision: string; description: string }[];
  round_trip_ms: number | null;
  database_region: string | null;
  application_region: string | null;
}

/*
 * Write contracts. Record references are omitted so the API allocates the next project reference;
 * statuses a record starts in are set by the API and cannot be supplied.
 */

export interface RiskCreateInput {
  project_id: string;
  risk_name: string;
  probability: number;
  impact: number;
  status: string;
  mitigation_owner: string | null;
  mitigation_owner_user_id?: number | null;
  mitigation_status: string | null;
  due_date: string;
}

export interface IssueCreateInput {
  project_id: string;
  title: string;
  description: string;
  severity: Severity;
  owner: string | null;
  owner_user_id?: number | null;
  raised_date: string;
  target_resolution_date: string | null;
  source_reference: string | null;
}

export interface AssumptionCreateInput {
  project_id: string;
  assumption_text: string;
  owner: string;
  owner_user_id?: number | null;
  validation_due_date: string | null;
  impact_if_false: string | null;
  source_reference: string | null;
}

export interface ChangeRequestCreateInput {
  project_id: string;
  requirement_id: string;
  change_description: string;
  reason: string;
  priority: string;
  requested_date: string;
}

export interface GateCreateInput {
  project_id: string;
  milestone_id: string | null;
  gate_name: string;
  planned_review_date: string;
  owner: string;
  applicable_baseline: string | null;
}

export interface GateCriterionCreateInput {
  criterion_type: "Entry" | "Exit";
  criterion_name: string;
  description: string;
  is_mandatory: boolean;
  evidence_required: boolean;
}

export type DependencyEndpointType = "Task" | "Milestone" | "Supplier" | "External" | "Customer";

export interface DependencyCreateInput {
  project_id: string;
  predecessor_type: DependencyEndpointType;
  predecessor_id: string;
  successor_type: "Task" | "Milestone";
  successor_id: string;
  dependency_name: string;
  relationship_type: Dependency["relationship_type"];
  lag_days: number | null;
  status: string;
  delay_days: number;
  criticality: string;
}

export interface ActionCreateInput {
  project_id: string;
  action_description: string;
  owner: string | null;
  owner_user_id: number | null;
  due_date: string;
  priority: string;
  source_reference: string | null;
}

export interface TestCaseCreateInput {
  project_id: string;
  test_case_name: string;
  owner: string | null;
}

export interface ResourceCreateInput {
  project_id: string;
  resource_name: string;
  allocated_hours: number;
  capacity_hours: number;
  week_start_date: string;
}
