# Change Impact Methodology

Change impact analysis in EPOS Lite is deterministic, evidence-based traversal and estimation.
It is implemented in `src/change_impact_engine.py`, is unit-tested like the Health, Confidence and
Risk engines, and **involves no AI of any kind**. Every artefact it returns is a real record ID
from the loaded portfolio.

Public API:
- `calculate_change_impact(change_request_id, portfolio, as_of_date) -> ChangeImpactResult`
- `list_change_requests_for_project(project_id, portfolio) -> list[ChangeRequest]`

`calculated_at` is midnight UTC on `as_of_date`, matching the other engines. `PortfolioData` is
read-only throughout.

## Traversal algorithm
1. Resolve the change request by `change_request_id`; an unknown ID raises `DataValidationError`
   naming the ID.
2. Resolve the linked requirement via `change_request.requirement_id`, scoped to the change
   request's project. If it does not exist, raise `DataValidationError` naming the requirement,
   rather than returning an empty result.
3. Follow every `trace_links` record where `source_type = "Requirement"` and `source_id` is the
   changed requirement, restricted to the same project. The target must exist in the loaded data.
4. For each affected **task**, collect any `dependencies` record where that task appears as
   `predecessor_id` or `successor_id`, and add the artefact at the other end of that dependency
   (a Task or a Milestone).
5. For each affected task, add the milestone it belongs to via its own `milestone_id`.
6. Return unique, sorted lists of affected task, test case, dependency and milestone IDs.

## Link types traversed
Only requirement-sourced link types that actually exist in the Version 1 data model:

| link_type | Target | Why it is traversed |
|-----------|--------|---------------------|
| `implemented_by` | Task | The work that realises the requirement is directly affected by a change to it. |
| `verified_by` | TestCase | Verification evidence must be re-examined when the requirement changes (the same relationship Risk Rule 8 uses). |
| `delivered_in` | Milestone | The delivery point the requirement is committed to. |

No other requirement-sourced link types exist in the data, and none are invented.

## Schedule-impact estimate
A single value in **calendar days**, looked up from `CHANGE_IMPACT_SCHEDULE_DAYS` in
`src/scoring_rules.py` using the **highest criticality among affected milestones** and the
**change request's priority**:

| Milestone criticality / Change priority | Critical | High | Medium | Low |
|------------------------------------------|----------|------|--------|-----|
| Critical | 20 | 15 | 10 | 5 |
| High | 15 | 10 | 7 | 3 |
| Medium | 10 | 7 | 5 | 2 |
| Low | 5 | 3 | 2 | 1 |

If no milestone is affected, the estimate is **0** (`CHANGE_IMPACT_NO_MILESTONE_DAYS`).

> This is a coarse Version 1 heuristic for demonstration purposes. It is **not** a validated
> project-management forecasting or estimation methodology, and must not be presented as one.

## Risk level rule
Assigned deterministically from the same evidence, where `artefact_count` is the total number of
affected tasks, test cases, milestones and dependencies:

1. `artefact_count == 0` → **Low**
2. highest affected milestone criticality is `Critical` **and** change priority is `High` or
   `Critical` → **Critical**
3. highest affected milestone criticality is `Critical` or `High` → **High**
4. `artefact_count >= 5` (`CHANGE_IMPACT_BREADTH_THRESHOLD`) → **High**
5. otherwise → **Medium**

## Empty results
A change request whose requirement has no trace links is a **valid outcome, not an error**, but it
is **not an assessment**. The engine returns an empty result with
`evidence_status = "Insufficient evidence"`, an explanation saying the impact cannot be assessed
until the requirement is traced, and a limitation noting that an empty result may indicate
incomplete trace-link data rather than a genuinely low-impact change. `risk_level` stays `Low`
for compatibility, but the interfaces show **Insufficient evidence** / **Not assessed** instead of
the Low label, so a data gap is never presented as safety. Every traced result has
`evidence_status = "Assessed"`.

## Known limitations
- **The legacy CSV change-impact model has no distinct release entity.** It represents release
   points as milestones such as `M-203` and `M-703`, so this engine reports affected milestones and
   does not fabricate releases. EPOS Next has first-class governed Gate records, but this engine
   does not yet traverse them; see [Gate readiness](gate-readiness-methodology.md).
- Milestone-to-milestone dependency chains are not followed; dependency traversal starts from
  affected tasks only.
- Traversal is single-pass: dependencies of tasks discovered through other dependencies are not
  re-traversed transitively.
- The schedule estimate is a lookup heuristic, as stated above.
- All data is synthetic.
