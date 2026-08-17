# Data Dictionary

All Version 1 data is synthetic and stored as CSV in `data/`. Dates use ISO format
`YYYY-MM-DD`. Booleans use `TRUE`/`FALSE`. Primary keys are unique within their file.

## projects.csv
| Field | Type | Notes |
|-------|------|-------|
| project_id | str (PK) | e.g. `P-002` |
| project_name | str | |
| domain | str | e.g. Sustainability, Digital Engineering |
| project_manager | str | |
| start_date | date | |
| baseline_end_date | date | Planned finish |
| forecast_end_date | date | Current forecast finish |
| status_update_date | date | Last time status was refreshed |
| project_phase | str | e.g. Execution |
| business_priority | str | High / Medium / Low |

## milestones.csv
| Field | Type | Notes |
|-------|------|-------|
| milestone_id | str (PK) | e.g. `M-202` |
| project_id | str (FK→projects) | |
| milestone_name | str | |
| baseline_date | date | |
| forecast_date | date | Later than baseline ⇒ slip |
| status | str | Planned / In Progress / At Risk / Completed |
| criticality | str | Low / Medium / High / Critical |
| owner | str | |

## tasks.csv
| Field | Type | Notes |
|-------|------|-------|
| task_id | str (PK) | |
| project_id | str (FK→projects) | |
| milestone_id | str (FK→milestones) | |
| task_name | str | |
| owner | str | |
| status | str | Not Started / In Progress / Blocked / Completed |
| planned_end_date | date | |
| forecast_end_date | date | |
| completion_percent | int 0–100 | |
| is_blocked | bool | |
| last_updated_date | date | Old date ⇒ stale |

## risks.csv
| Field | Type | Notes |
|-------|------|-------|
| risk_id | str (PK) | |
| project_id | str (FK→projects) | |
| risk_name | str | |
| probability | int 1–5 | |
| impact | int 1–5 | |
| status | str | Open / Closed |
| mitigation_owner | str (optional) | Blank ⇒ ownership gap |
| mitigation_status | str (optional) | |
| due_date | date | |

## dependencies.csv
| Field | Type | Notes |
|-------|------|-------|
| dependency_id | str (PK) | |
| project_id | str (FK→projects) | |
| predecessor_type | str | Supplier / Task / Milestone |
| predecessor_id | str | |
| successor_type | str | Task / Milestone |
| successor_id | str | |
| dependency_name | str | |
| status | str | On Track / Delayed |
| delay_days | int ≥ 0 | Working days of delay |
| criticality | str | Low / Medium / High / Critical |

## actions.csv
| Field | Type | Notes |
|-------|------|-------|
| action_id | str (PK) | |
| project_id | str (FK→projects) | |
| action_description | str | |
| owner | str (optional) | |
| due_date | date | Past + Open ⇒ overdue |
| status | str | Open / Closed |
| priority | str | High / Medium / Low |
| source_reference | str | ID of related record |

## resources.csv
| Field | Type | Notes |
|-------|------|-------|
| resource_id | str (PK) | |
| resource_name | str | |
| project_id | str (FK→projects) | |
| allocated_hours | int ≥ 0 | |
| capacity_hours | int > 0 | |
| week_start_date | date | allocated > capacity ⇒ overallocation |

## requirements.csv
| Field | Type | Notes |
|-------|------|-------|
| requirement_id | str (PK) | |
| project_id | str (FK→projects) | |
| requirement_text | str | |
| requirement_type | str | Functional / Non-Functional |
| priority | str | High / Medium / Low |
| status | str | Draft / Approved / Changed |
| owner | str | |
| last_updated_date | date | |

## test_cases.csv
| Field | Type | Notes |
|-------|------|-------|
| test_case_id | str (PK) | |
| project_id | str (FK→projects) | |
| test_case_name | str | |
| status | str | Not Run / Passed / Failed |
| owner | str | |
| verification_evidence | str (optional) | Blank ⇒ verification gap |
| last_updated_date | date | |

## trace_links.csv
| Field | Type | Notes |
|-------|------|-------|
| trace_link_id | str (PK) | |
| project_id | str (FK→projects) | |
| source_type | str | Requirement / Task / TestCase / Milestone |
| source_id | str | |
| target_type | str | Requirement / Task / TestCase / Milestone |
| target_id | str | |
| link_type | str | implemented_by / verified_by / delivered_in |

## change_requests.csv
| Field | Type | Notes |
|-------|------|-------|
| change_request_id | str (PK) | e.g. `CR-042` |
| project_id | str (FK→projects) | |
| requirement_id | str (FK→requirements) | |
| change_description | str | |
| reason | str | |
| priority | str | High / Medium / Low |
| status | str | Proposed / Approved / Rejected |
| requested_by | str | |
| requested_date | date | |

## Relationships
```
Project 1─* Milestone 1─* Task
Project 1─* Risk
Project 1─* Action
Project 1─* Resource allocation
Project 1─* Requirement
Requirement *─* Task        (trace_links: implemented_by)
Requirement *─* Test Case   (trace_links: verified_by)
Requirement *─* Milestone   (trace_links: delivered_in)
Change Request *─1 Requirement ─ linked Task/Test/Milestone
Dependency: predecessor artefact ─▶ successor artefact
```

## Canonical status vocabulary and accepted aliases
Source CSV values are preserved as written. During loading, status/priority values are normalised
internally to the canonical values below (defined in `src/scoring_rules.py`). Matching is
case-insensitive and whitespace-tolerant (for example ` completed ` → `Complete`). Values that do
not map to a canonical value are **not** treated as healthy: they are recorded as
`PortfolioData.status_anomalies` and surfaced through the Data Confidence score.

| Domain (fields) | Canonical values | Example aliases |
|-----------------|------------------|-----------------|
| Schedule — project/milestone/task `status` | Not Started, In Progress, On Track, At Risk, Delayed, Blocked, Complete, Closed, Cancelled | Completed→Complete, Done→Complete, WIP→In Progress |
| Risk `status` | Open, Mitigating, Closed, Accepted | in mitigation→Mitigating |
| Mitigation `mitigation_status` | Not Started, In Progress, Complete, Not Required | completed→Complete, n/a→Not Required |
| Action `status` | Open, In Progress, Complete, Closed, Cancelled | completed→Complete |
| Dependency `status` | On Track, At Risk, Delayed, Blocked, Complete, Closed, Resolved | completed→Complete |
| Requirement `status` | Draft, Approved, Changed, Superseded, Retired | — |
| Test case `status` | Not Run, Passed, Failed | pass→Passed, fail→Failed |
| Priority/criticality | Low, Medium, High, Critical | crit→Critical, med→Medium |

**Terminal statuses** (excluded from delivery penalties): schedule/action `Complete, Closed,
Cancelled`; dependency `Complete, Closed, Resolved`; risk `Closed`.
**Active requirement statuses** (in scope for verification checks): `Approved, Changed`.

## Freshness fields
Data Confidence measures recency using these fields relative to the caller's `as_of_date`
(calendar days): `projects.status_update_date`, `tasks.last_updated_date`,
`requirements.last_updated_date`, `test_cases.last_updated_date`. Freshness bands: fresh 0–7,
stale 8–14, significantly stale 15–21, critically stale >21.

## Nullable fields and the active/terminal distinction
Some date/attribution fields are **optional** (may be blank in a source row, loaded as `None`) so
that "missing data" is representable and surfaced by Data Confidence rather than silently assumed:
`projects.baseline_end_date`, `projects.forecast_end_date`, `projects.status_update_date`,
`milestones.baseline_date`, `milestones.forecast_date`, `tasks.last_updated_date`,
`requirements.last_updated_date`, `test_cases.last_updated_date`, `change_requests.requested_by`,
and the various `owner`/`mitigation_owner` fields. Real synthetic CSVs populate all of these.

Confidence factors operate on **active** records only, excluding canonical terminal statuses
(`Complete/Closed/Cancelled` for schedule/actions; `Superseded/Retired` for requirements). Active
requirements are `Approved`/`Changed`; active change requests are any status other than `Rejected`.

**Completeness required fields** (per entity, active records) exclude the ownership fields
(`owner`, `mitigation_owner`, `requested_by`) — those are scored solely by Ownership Coverage.

## Change-impact relationships
The change-impact engine traverses only relationships already present above:
`change_requests.requirement_id` to `requirements`, then `trace_links` where
`source_type = Requirement` (`implemented_by` to Task, `verified_by` to TestCase, `delivered_in` to
Milestone), then `dependencies` whose `predecessor_id`/`successor_id` reference an affected task,
then each affected task's own `milestone_id`.

The legacy CSV analysis model has no distinct release entity or `release_id`; release-named records
such as `M-203` and `M-703` remain milestones for change-impact traversal. EPOS Next persistence
also contains first-class governed Gates, Gate Criteria, and immutable Gate Reviews. Those records
drive [Gate readiness](gate-readiness-methodology.md) but are not yet inputs to the legacy
change-impact engine.

## Source tables: critical vs optional (Version 1)
Used by the Source Reliability factor ("Prototype data-source availability assessment").
- **Critical:** `projects`, `milestones`, `tasks`, `risks`. If project-level data cannot load or
  validate, no confidence score is produced (a `DataValidationError` is raised).
- **Optional:** `dependencies`, `actions`, `resources`, `requirements`, `test_cases`,
  `trace_links`, `change_requests`. A missing optional table lowers Source Reliability but the
  system continues with partial data. "Unavailable" means the table has no records at all; a table
  populated only for other projects is not a penalty for this project.
