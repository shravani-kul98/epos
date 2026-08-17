# Gate Readiness Methodology

EPOS Next treats a Gate as a governed project review point. Deterministic Python calculates
readiness from stored Gate criteria and immutable human reviews. The calculation never approves a
Gate, creates criteria, or infers missing evidence.

## Authoritative inputs

For the current review cycle, readiness uses only:

- the Gate record and its applicable-baseline reference;
- live Gate Criterion records, including mandatory/optional classification, assessment status,
  and evidence requirement;
- the immutable Gate Review recorded by an authorized human reviewer.

Every blocker and warning includes the Gate, criterion, or review record IDs that support it.
Calculation timestamp and methodology version are returned by the API.

## Criterion completion

A criterion is complete only when its stored status is `Met` and, when evidence is required, its
evidence reference is non-empty. A `Met` status cannot bypass missing required evidence.

When at least one criterion exists, the displayed percentage is:

```text
round(100 * complete criteria / configured criteria)
```

When no criteria are configured, percentage is `null`, not zero, and the Gate has a mandatory
blocker. An incomplete mandatory criterion is a blocker. An incomplete optional criterion is a
warning. A percentage never overrides a mandatory blocker.

## Readiness states

| Evidence state | Readiness |
|---|---|
| Any blocker, including no criteria, mandatory incompletion, rejected review, or deferred review | Not Ready |
| Criteria have no blockers and no current-cycle review exists | Ready for Review |
| Criteria have no blockers and the current human review is Approved | Approved |
| Criteria have no blockers and the current human review is Approved with Conditions | Approved with Conditions |

Conditional approval requires recorded conditions. Rejected and deferred review outcomes remain
blockers with their review ID. Reopening a failed or deferred Gate starts a new review cycle; prior
reviews remain immutable history but do not stand in for a decision in the new cycle.

## Controlled lifecycle

Gate status can change only through the transition endpoint. Configuration is frozen after the
Gate leaves preparation, criteria can be assessed only while `Preparing`, and reviews can be
submitted only while `In Review`. Passing transitions require matching deterministic readiness:

- `Passed` requires `Approved`;
- `Passed with Conditions` requires `Approved with Conditions`;
- `Failed` requires a current-cycle `Rejected` review;
- review-based `Deferred` requires a current-cycle `Deferred` review.

Gate Review rows have database triggers that reject update and delete operations. The API exposes
creation and read operations only. This makes a human decision append-only rather than editable
approval text.

## Current boundary

Version 1.0 deliberately does not invent thresholds over risks, actions, changes, requirements,
trace links, dependencies, or milestones. Those records may become readiness inputs only through
future documented deterministic adapters. The current applicable-baseline value and criterion
evidence references are governed references supplied by humans; EPOS does not infer them.