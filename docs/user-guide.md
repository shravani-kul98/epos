# EPOS user guide

This guide explains EPOS in plain words for people using it day to day. Ask EPOS reads it to
answer "how do I" and "what is" questions.

## What is EPOS

EPOS (Engineering Portfolio Operating System) is one place to see how engineering projects are
doing. It brings together each project's plan, tasks, risks, requirements, tests and decisions,
and calculates two scores for every project:

- **Health** says how delivery is going, from 0 to 100.
- **Confidence** says how complete and up to date the recorded data is, from 0 to 100.

The scores are calculated by fixed rules from your records, never by AI. EPOS then shows what
needs attention and why, with links back to the records behind each number. People make the
decisions; the AI only explains.

## Getting started

1. Sign in with your work email and password.
2. Open **My Work** to see the tasks and actions assigned to you.
3. Open **Inbox** for assignments, review requests and other messages.
4. Open **Projects** and choose a project to see its plan, risks and evidence.
5. Ask **Ask EPOS** anything in your own words, for example "what should I do today?".

What you see depends on your role. If a page or button is missing, your role probably does not
include it; see "Roles and access" below.

## Pages

- **Executive summary** or **Overview** (the start page): what needs attention, critical alerts,
  key numbers and your own work.
- **Portfolio**: every project you can see, with health, confidence and alerts. Click a number to
  filter the list.
- **My Work**: tasks and actions assigned to you, what is due, overdue or blocked. Accept or
  decline new assignments here.
- **Inbox**: assignments, review requests, blocked work and other notifications. Use
  **Mark as read** when you have dealt with one.
- **Calendar**: forecast dates for milestones and tasks, risk due dates and when change
  requests were raised.
- **Projects**: the project list. Open a project to see its workspace (tabs below).
- **Risks**, **Issues**, **Requirements**, **Change requests** and **Decisions**: registers across
  all the projects you can see.
- **Executive report**: a weekly summary for leadership (roles with report access).
- **Scenarios**: "what if" simulations, for example a supplier delivering late (roles that may
  run scenarios). Nothing is changed by a simulation.
- **Ask EPOS**: the assistant. It answers from your records and never changes anything.
- **Team & Access**: accounts, roles, invitations and workspace maintenance (Administrators).
- **Account**: open the account menu in the top bar and choose **Role and permissions** to see
  your role, change your password and see where you are signed in.

## Project workspace tabs

- **Overview**: the project's health, confidence, next milestone, blocked work and actions.
- **Delivery plan**: milestones, tasks, dependencies and the delivery timeline.
- **Team members**: who works on the project.
- **Capacity & actions**: weekly allocations of people and follow-up actions.
- **Risks**, **Issues**, **Assumptions**: the project's controls.
- **Change requests** and **Decisions**: proposed changes and the decisions taken on them.
- **Meetings**: meeting notes; EPOS suggests actions, risks and decisions found in them.
- **Requirements**: requirements, their tests and the evidence that verifies them.
- **Gates**: formal review points with criteria that must be met.
- **Audit trail**: who changed what and when.

## How to create a project

Choose **Create project** on the start page or in the top bar. A four-step form follows:
Project basics, Timeline and delivery (with an optional starter plan), Initial control setup
(a first risk), and Review and create. Project Managers, PMO Analysts and Administrators can
create projects.

## How to add a milestone or a task

Open the project, go to **Delivery plan** and choose **New milestone** or **New task**. A task
belongs to a milestone, has an assignee, a planned due date and an expected finish date. Tick
**Requires manager review** when a manager should check the work before it counts as complete.
Use **Add dependency** to record that one piece of work waits on another.

## How to accept or decline an assignment

When someone assigns you a task, it appears in **My Work** and **Inbox**. Choose **Accept**, or
**Decline** and say why. Declining returns the task to the manager.

## How to update or complete your task

Open the task from **My Work** or the project's **Delivery plan**. Change its status, the
percentage complete, or mark it blocked. Marking a task blocked needs a short note saying what
it is waiting for, so the right person can clear it. Add a progress note when something changes.
When the work is done, complete it. If the task requires manager review, the manager then
accepts it or returns it with a note.

## How to raise a risk, issue or assumption

Open the project and go to **Risks** (**New risk**), **Issues** (**Raise issue**) or
**Assumptions** (**Record assumption**). A risk has a probability and an impact from 1 to 5;
their product is its exposure. Give every serious risk a mitigation owner. A risk can only be
closed once its mitigation is Complete or Not Required.

## How to raise a change request or record a decision

Open the project and go to **Change requests** (**Raise change request**) or **Decisions**.
Someone other than the person who raised it decides a change request or a proposed decision, and
the outcome needs a written reason. Only an Administrator may decide their own, and the audit
trail records it.

## How to capture meeting notes

Open the project, go to **Meetings** and choose **Capture a meeting note**. Paste the notes.
EPOS lists the follow-ups it found (actions, risks and decisions); you choose which ones to
create and who owns them.

## How to change your password

Open the account menu in the top bar, choose **Role and permissions**, and use the **Password**
section. Changing it signs you out of your other sessions. If you forgot your password, ask a
workspace Administrator to reset it; you will then choose a new one when you sign in.

## Roles and access

Your role decides what you can see and change. The rules are enforced by the server, not just by
hiding buttons.

- **Engineer**: sees the projects they are a member of and updates their own tasks and actions.
- **Engineering Lead**, **Requirements Manager** and **Project Manager**: see and manage the
  projects they are members of, each for their own area.
- **PMO Analyst**: sees and manages every project.
- **Executive**: sees every project and the reports, and changes nothing.
- **Administrator**: everything, including accounts, roles and workspace maintenance.

New accounts start as Engineer. **Only an Administrator can change a role**, in
**Team & Access**. To get PMO Analyst or another role, ask your workspace Administrator.

## How to join a project

A Project Manager, PMO Analyst or Administrator adds you on the project's **Team members** tab
with **Add member**. Until then the project does not appear for an Engineer, Engineering Lead,
Requirements Manager or Project Manager.

## What the scores and colours mean

- **Health** 0 to 100: Green is 80 to 100, Amber is 60 to just under 80, Red is below 60.
  Health falls when milestones slip, tasks are overdue or blocked, risks are high and unowned,
  dependencies are late or people are overloaded.
- **Confidence** 0 to 100: High is 80 or more, Medium 60 to just under 80, Low below 60.
  Confidence falls when data is missing, stale or has no owner. Low confidence means "check the
  records before trusting the health score".
- **Needs attention**: a project with Amber or Red health, or at least one Critical alert.
- **Alerts** are early warnings such as a blocked task on a critical milestone or a risk with no
  mitigation owner.

## Using Ask EPOS

Ask in your own words, in any language, with typos if you like. Examples: "what's going on?",
"what do I have to do this week?", "why is the battery project red?", "who owns that risk?",
"what changed since last week?", "can we pass the gate?", "make it shorter". Ask EPOS remembers
the conversation, so follow-ups such as "why?", "and the second one?" or "which of those are
blocked?" work. Choose a project in the scope box to focus on it.

You can ask about any record and any of its details, not only common questions: "which
requirements have no test at all?", "average milestone slip per project", "anything mentioning
thermal?", "which domain has the lowest average health?", "who is over capacity, and by how
much?". EPOS itself finds, counts and totals the records, so the numbers are exact.

Ask EPOS reads the records you are allowed to see and never changes them. Calculated numbers
come from EPOS itself. AI-written explanations are drafts: check them against the sources, which
you can open under each answer.

## Common questions

- **Can I break something by clicking around?** No. Opening pages and records changes nothing.
  A record changes only when you save a form or confirm an action, and only where your role
  allows it. Every change is recorded in the project's **Audit trail** with who made it. Ask EPOS
  and Scenarios never change records.
- **Can the AI make mistakes?** Yes. AI-written explanations can be wrong or incomplete, so each
  one is marked as a draft for human review and lists the records it is based on; open them to
  check. Scores, dates and counts are calculated by EPOS itself, not by the AI.
- **Is my data safe?** What you can see and change is decided by your role and project
  membership, and the server enforces it. Passwords are stored only in a protected, one-way form
  and are never shown to anyone. Ask EPOS sends your question and only the records needed to
  answer it to your organisation's approved AI service. For anything else, ask your workspace
  Administrator.
- **I can't see a project.** An Engineer, Engineering Lead, Requirements Manager or Project
  Manager sees only the projects they are a member of; see "How to join a project". PMO Analysts,
  Executives and Administrators see every project.

## Glossary

- **Project**: a piece of engineering work with a start, a planned end and a manager.
- **Milestone**: an important checkpoint with a baseline (planned) date and a forecast date.
- **Task**: a piece of work towards a milestone, assigned to one person.
- **Action**: a follow-up that someone agreed to do, with an owner and a due date.
- **Dependency**: something that must happen first, for example a supplier delivery.
- **Risk**: something that might go wrong; exposure is probability times impact.
- **Issue**: something that has already gone wrong and needs handling.
- **Assumption**: something the plan relies on that still needs to be confirmed.
- **Requirement**: what the product must do; it is verified by tests with evidence.
- **Traceability**: the links between requirements, tasks and tests.
- **Change request**: a proposal to change a requirement or the plan; someone else decides it.
- **Decision**: a recorded choice with its reasoning.
- **Gate**: a formal review point where criteria must be met before moving on.
- **PMO**: Project Management Office, the team that oversees all projects. In EPOS the PMO
  Analyst role sees and manages every project.
- **Baseline** and **forecast**: the originally planned date and the currently expected date.
- **Slip**: how many days the forecast is later than the baseline.
