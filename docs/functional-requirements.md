# Functional Requirements — Version 1

IDs are for traceability within this document. "The system" refers to EPOS Lite.

## Data foundation
- **FR-01** The system shall load portfolio data from the CSV files in `data/`.
- **FR-02** The system shall validate every CSV against a typed schema and reject invalid rows
  with an explicit, human-readable error.
- **FR-03** The system shall detect missing required columns and duplicate primary IDs.
- **FR-04** The system shall check referential integrity (e.g. every `project_id` on a child
  record exists in `projects.csv`).

## Portfolio Dashboard
- **FR-10** The system shall show total project count and Green/Amber/Red counts.
- **FR-11** The system shall show average Health and average Confidence scores.
- **FR-12** The system shall list critical risks without owners, overdue actions and at-risk milestones.
- **FR-13** The system shall show a Health-vs-Confidence scatter plot.
- **FR-14** The system shall show a top-exceptions table and allow filtering by project/domain/status.

## Project Intelligence
- **FR-20** The system shall show a project's Health score, band and factor breakdown.
- **FR-21** The system shall show a project's Confidence score, band and data-quality issues.
- **FR-22** The system shall show milestones, tasks, risks, actions and dependencies for the project.
- **FR-23** The system shall show a plain-language "Why this status?" explanation for every score.
- **FR-24** The system shall list early-warning alerts with severity and source IDs.

## Requirements Traceability
- **FR-30** The system shall list requirements with status, priority and owner.
- **FR-31** The system shall show linked tasks, test cases and milestones per requirement.
- **FR-32** The system shall flag traceability gaps (no task, no test, no verification evidence).
- **FR-33** The system shall provide an at-risk requirements view.

## Change Impact
- **FR-40** The system shall let a user select a change request and show its linked requirement.
- **FR-41** The system shall compute affected tasks, tests, dependencies and milestones deterministically.
- **FR-42** The system shall show a deterministic impact assessment with source IDs.
- **FR-43** The system shall offer optional GPT-4o engineering and executive summary drafts.
- **FR-44** The system shall let a user approve/edit/reject an AI draft and record it in a local approval log.

## Scenario Planner
- **FR-50** The system shall simulate supplier_delay, task_delay, resource_overallocation and missing_update.
- **FR-51** The system shall recalculate Health and Confidence on a temporary scenario dataset.
- **FR-52** The system shall compare baseline vs scenario and list affected artefacts and alerts.
- **FR-53** The system shall never mutate baseline CSV data and shall state that results are simulated.

## Ask EPOS (GPT-4o)
- **FR-60** The system shall offer a fixed set of supported questions plus optional controlled text input.
- **FR-70** The system shall build a selected, validated evidence package (not the whole dataset).
- **FR-71** The system shall validate the AI response into a strict `CopilotResponse` model.
- **FR-72** The system shall show source IDs, a human-review warning and the standard disclaimer.
- **FR-73** The system shall remain fully functional for deterministic features when AI is unavailable.
