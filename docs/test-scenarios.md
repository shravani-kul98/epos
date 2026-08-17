# Manual Acceptance Test Scenarios

These are manual, evidence-based acceptance tests for a reviewer. Automated unit tests live in
`tests/`. All data is synthetic (P-002, P-007).

## AT-01 — Supplier delay is visible and downstream-only
1. Open **Scenario Planner**, select dependency `D-2001` (Supplier → `M-202`), delay 30 working days.
2. **Expect:** `M-202` (and downstream `M-203`) forecast dates move; P-002 Health drops; a banner
   states results are simulated; baseline CSVs are unchanged (re-open Portfolio Dashboard to confirm).

## AT-02 — High-impact unowned risk raises a Critical alert
1. Open **Project Intelligence** for P-002.
2. **Expect:** risk `R-2001` (impact 5, no mitigation owner) produces a **Critical** early-warning
   alert with `source_ids` including `R-2001`, and recommends assigning a mitigation owner.

## AT-03 — Stale updates reduce Confidence
1. Open **Project Intelligence** for P-007 (status updated 2026-07-05; tasks last updated early July).
2. **Expect:** Confidence is lower than P-002; Data Freshness factor explanation names the stale
   records; data-quality issues list the stale updates.

## AT-04 — Missing verification evidence is a traceability gap
1. Open **Requirements Traceability**, filter at-risk requirements.
2. **Expect:** `REQ-7002` is flagged — test `TC-7002` is Failed with no verification evidence; the
   gap description names the missing evidence; risk level is elevated.

## AT-05 — Change request impact is complete and grounded
1. Open **Change Impact**, select `CR-042`.
2. **Expect:** linked requirement `REQ-7001`; affected task `T-7001`, test `TC-7003`, milestone
   `M-702`; deterministic impact with `source_ids`; optional GPT-4o drafts labelled as review-required.

## AT-06 — Grounded AI response with source IDs
1. Open **Ask EPOS**, choose "Which risks have no mitigation owner?".
2. **Expect:** response lists `R-2001` and `R-7001`; every `source_id` exists in the evidence
   package; disclaimer present; human-review warning shown.

## AT-07 — AI unavailable is safe
1. Temporarily run without Azure config (unset environment variables in a separate shell).
2. **Expect:** Ask EPOS shows the safe "AI capability is unavailable…" message; Portfolio Dashboard,
   Project Intelligence, Traceability, Change Impact (deterministic part) and Scenario Planner all
   continue to work.

## AT-08 — Overdue action and blocked task surface on the dashboard
1. Open **Portfolio Dashboard**.
2. **Expect:** overdue actions include `A-2001`/`A-7001`; at-risk milestones include `M-202`,
   `M-702`; blocked tasks `T-2001`/`T-7002` appear in project exceptions.

## Health engine manual verification (Phase 3)
These use `calculate_project_health(project_id, portfolio, as_of_date)` with a fixed
`as_of_date = 2026-08-25`. They require no UI, network or Azure key.

- **HE-01 On-track project:** a project with an on-time forecast, on-track milestones, no blocked or
  overdue tasks, low risks, on-track dependencies, allocations <= 90% and no overdue actions scores
  Green (near 100) with no Critical drivers.
- **HE-02 Major schedule slip:** a forecast end date more than 20 calendar days past baseline gives
  a schedule performance factor of 25 and a Critical schedule driver citing the project ID.
- **HE-03 Blocked critical-milestone task:** a blocked task linked to a Critical milestone reduces
  task execution by 15 and produces a Critical `task_execution` driver citing the task and milestone.
- **HE-04 Unowned high-exposure risk:** an Open probability-5 impact-5 risk with no mitigation owner
  reduces risk exposure by 35 and produces a Critical `risk_exposure` driver citing the risk ID.
- **HE-05 Delayed dependency:** a Delayed Critical dependency with `delay_days > 0` reduces
  dependency status by 20 and produces a Critical `dependency_status` driver.
- **HE-06 Resource overload:** an allocation above 110% utilisation reduces resource capacity and
  produces a High/Critical `resource_capacity` driver stating the exact utilisation.
- **HE-07 Overdue action:** an overdue High or Critical action reduces action closure and produces a
  matching driver stating the days overdue.
- **HE-08 Unavailable optional dataset:** with no dependency records at all, dependency status uses
  the fallback score 70 and records an explicit limitation (not an adverse penalty). Verify P-002
  and P-007 from the real synthetic data produce different Red results with project-scoped evidence.

## Early-warning engine manual verification (Phase 3)
These use `generate_early_warnings(project_id, portfolio, as_of_date)` with a fixed
`as_of_date = 2026-08-25`. No UI, network or Azure key is required.

- **EW-01 Rule 1 (unowned high-exposure risk):** for P-002, `R-2001` (Open, probability 4, impact 5,
  no mitigation owner) produces a **Critical** `unowned_high_exposure_risk` alert citing `R-2001`.
- **EW-02 Rule 2 (critical milestone slip):** a Critical milestone forecast more than 10 calendar
  days after baseline produces a **Critical** `critical_milestone_slip` alert.
- **EW-03 Rule 3 (delayed dependency):** a Delayed dependency (`delay_days > 10`) linked to a
  Critical milestone produces a **Critical** `milestone_delayed_dependency` alert citing both IDs.
- **EW-04 Rule 4 (blocked task):** a blocked task linked to a Critical milestone produces a
  **Critical** `blocked_task_critical_milestone` alert citing the task and milestone.
- **EW-05 Rule 5 (overdue action):** a Critical-priority action overdue by more than 7 days produces
  a **Critical** `overdue_high_priority_action` alert.
- **EW-06 Rule 6 (resource over-allocation):** a resource above 125% utilisation produces a
  **Critical** `resource_over_allocation` alert stating the exact utilisation.
- **EW-07 Rule 7 (stale status):** P-007 (status 51 days old at the reference date) produces a
  **High** `stale_project_status` alert; a project with no status date produces a **Critical** one.
- **EW-08 Rule 8 (requirement verification):** for P-007, `REQ-7002` (linked test Failed, no
  evidence) produces a **High** `requirement_missing_verification` alert; `REQ-7001` (linked test
  Not Run) produces a **Medium** one. This uses only the existing `verified_by` trace link.

## Confidence engine manual verification (Phase 3)
These use `calculate_project_confidence(project_id, portfolio, as_of_date)` with a fixed
`as_of_date = 2026-08-25`. No UI, network or Azure key is required.

- **DC-01 Fresh/complete/owned project:** a project with a recent status update, complete required
  fields, all owners assigned and every source table present scores **High** with all four factors
  at 100 and no High/Critical issues.
- **DC-02 Freshness — project status age:** status 8–14 days old reduces freshness by 10, 15–21 by
  20, >21 by 35, and a **missing** status date by 40 (Critical issue). P-007 (51 days) is
  critically stale.
- **DC-03 Freshness — active records:** when more than 50% of active tasks/requirements/test cases
  are older than 7 days or missing `last_updated_date`, freshness drops by 40; terminal records are
  excluded.
- **DC-04 Completeness:** missing required non-ownership fields lower completeness by band; a
  missing project date is flagged as a **High** severity data-quality issue.
- **DC-05 Ownership coverage:** unowned active tasks/risks/actions/requirements/change requests
  reduce ownership coverage per record, each capped (e.g. risks −10 each, cap −35).
- **DC-06 Source reliability:** all tables present → 100; an optional table entirely empty → 70; a
  critical table (milestones/tasks/risks) empty → 40 with a High issue; the `projects` table empty
  raises `DataValidationError`. A table populated only for another project is **not** penalised.
- **DC-07 Health vs Confidence:** a project with an on-time forecast and on-track milestone/task but
  a missing status date and missing task `last_updated_date` stays **Green** on Health while
  Confidence is **Low/Medium** — demonstrating why both must be read together.

## Phase 3 integration scope (Health + Confidence + Risk together)
`tests/test_phase3_integration.py` runs all three engines against the real synthetic data for
P-002 and P-007 with `as_of_date = 2026-08-25`. At a high level it verifies: the real portfolio
loads cleanly; all three engines return fully populated, project-scoped results; known adverse
signals surface in the correct project only; the two projects produce distinct, non-perfect Health
and Confidence scores and different alert sets; Health and Confidence are independent; a full
multi-engine run mutates no source data; a Critical alert never coincides with a Green Health band;
repeated execution is byte-identical; portfolio-level functions match project-level results; and an
unknown project raises the same `DataValidationError` across all three engines. Observed results are
recorded in [phase3-summary.md](phase3-summary.md).
