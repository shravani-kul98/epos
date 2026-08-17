# EPOS access by role

This is the short operational guide to who can see and change what in EPOS. The backend enforces
these rules on every API request; hiding a button in the interface is not treated as security.

## Scope rules

- **Executive, PMO Analyst and Administrator** can read every project.
- **PMO Analyst and Administrator** can write across every project.
- **Engineer, Engineering Lead, Requirements Manager and Project Manager** can see and change only
  projects to which they have been assigned as members.
- A Project Manager or PMO Analyst who creates a project is automatically added to it.
- Self-registration always creates an **Engineer** account. Only an Administrator can change roles
  or disable accounts.
- All signed-in roles may use Ask EPOS, but answers contain only records that role may access.

## Role summary

| Role | Can see | Can change |
| --- | --- | --- |
| **Executive** | Every project, portfolio analysis and executive reports | Nothing; read-only |
| **Engineer** | Assigned projects and their records | Status, completion percentage, blocker state and progress notes on tasks assigned to their own account, and the status of actions assigned to them |
| **Engineering Lead** | Assigned projects and reports | Delivery plans and work, actions, risks, issues and assumptions in assigned projects; may run scenarios |
| **Requirements Manager** | Assigned projects, reports and test/trace evidence | Requirements, assumptions, proposed decisions and new change requests in assigned projects; may run scenarios |
| **Project Manager** | Assigned projects and reports | Creates projects; manages project details, membership, delivery work, actions, risks, issues, assumptions, requirements, changes and decisions in assigned projects; may run scenarios |
| **PMO Analyst** | Every project and report | Same broad project-management capabilities as Project Manager, but across the whole portfolio |
| **Administrator** | Everything | Everything, including project deletion, users, roles, account activation and workspace administration |

## Detailed permission matrix

Legend: **Yes** allowed, **No** not allowed. Project membership and global-scope rules above still
apply.

| Capability | Executive | Engineer | Eng. Lead | Req. Manager | Project Manager | PMO Analyst | Administrator |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Read authorized portfolio/projects | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Ask EPOS | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Read executive reports | Yes | No | Yes | Yes | Yes | Yes | Yes |
| Run scenarios | No | No | Yes | Yes | Yes | Yes | Yes |
| Create projects | No | No | No | No | Yes | Yes | Yes |
| Edit project details | No | No | No | No | Yes | Yes | Yes |
| Delete projects | No | No | No | No | No | No | Yes |
| Manage project members | No | No | No | No | Yes | Yes | Yes |
| Update own assigned task progress | No | Yes | Yes | No | Yes | Yes | Yes |
| Manage delivery work and assignments | No | No | Yes | No | Yes | Yes | Yes |
| Manage actions | No | No | Yes | No | Yes | Yes | Yes |
| Manage risks | No | No | Yes | No | Yes | Yes | Yes |
| Manage issues | No | No | Yes | No | Yes | Yes | Yes |
| Manage assumptions | No | No | Yes | Yes | Yes | Yes | Yes |
| Manage requirements | No | No | No | Yes | Yes | Yes | Yes |
| View test cases and trace links | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Create change requests/decisions | No | No | No | Yes | Yes | Yes | Yes |
| Decide or withdraw changes/decisions | No | No | No | No | Yes | Yes | Yes |
| Manage users and roles | No | No | No | No | No | No | Yes |
| Administer the workspace | No | No | No | No | No | No | Yes |

## What “manage delivery work” includes

This covers tasks, milestones, work packages, deliverables, dependencies, gates, weekly capacity
allocations and meeting notes.
An Engineer does **not** receive this broad capability: they may update only their own assigned
task's progress, status and blocker flag, and add progress notes to it. Engineering Leads may
prepare gates and criteria, but a final governed gate review requires change-decision authority,
which starts at Project Manager.

Requirements managers define test cases, record their results with evidence and maintain trace
links from a requirement's panel, with the evidence and audit rules above.

## Governed records in the interface

Every form below leaves the record reference to EPOS, which allocates the next one in the project
(for example `ISS-P-002-003`). Starting states are set by EPOS, and each lifecycle step asks for
the reason, which is kept in the project's **Audit trail**.

| Record | Where | Who | Lifecycle in the interface |
| --- | --- | --- | --- |
| Risk | **Risks → New risk** | Manage risks | Status and mitigation edited in the risk panel; closing or accepting needs a reason |
| Issue | **Issues → Raise issue** | Manage issues | Start work, Resolve (with the resolution summary), Close, Reopen |
| Assumption | **Assumptions → Record assumption** | Manage assumptions | Validate or Invalidate with evidence, Retire, Return to proposed |
| Change request | **Change requests → Raise change request** | Create change requests | Decided in its panel by a person who can decide changes |
| Gate | **Gates → New gate** | Manage delivery work | Add criteria while Not Started or Preparing; assess them while Preparing; Mark ready, Begin review; the review decision needs change-decision authority; then close the gate as the review supports |
| Dependency | **Delivery plan → Add dependency** | Manage delivery work | Recorded with its relationship and lag; cycles and duplicate edges are refused |
| Action | **Capacity & actions → New action** | Manage actions | Assignees move their own actions from My Work |
| Weekly allocation | **Capacity & actions → Record allocation** | Manage delivery work | Corrected or withdrawn through the API |
| Test case | A requirement's **Linked work and tests → Define and link** | Manage requirements | Results recorded with evidence; a pass needs named evidence |

## After a password reset

An Administrator's **Reset password** issues a one-time temporary password. When the person signs
in with it, EPOS shows only **Choose a new password** until they replace it; the API refuses every
other request in the meantime. Saving the new password signs them straight back in.

## Assigning and completing tasks in the interface

1. A registered person has an active account. Only an Administrator assigns their EPOS role using
  the **Team & Access** dropdown and confirmation.
2. A PMO Analyst, Project Manager or Administrator adds the person through the project's
  **Team members → Add member** account dropdown. Engineering Leads can assign work but cannot
  grant project membership.
3. In **Delivery plan**, choose **New task**, select a milestone and **Assigned to**, enter dates,
  and save. If the project has no milestones, the form offers **Add the first milestone**.
4. Reassign an existing task with its visible **Edit / assign** button. Accounts with the same name
  are distinguished by email; the backend records the selected user ID. Historical owner text is
  marked **Not linked to an account** until explicitly assigned.
5. The assignee sees the task in **My Work** and can **Update progress** or **Mark complete**.
  Completion sets Complete/100%, clears the blocker flag, records the reporting date, and appends
  a named audit event. Actual work dates are not invented. Reopening is also audited.
  Either action accepts an optional note (up to 1,000 characters), so an update at 30% or a
  completion can say what was done, what comes next or what is in the way. A note on its own is
  also a progress report and refreshes the reporting date. Notes are kept in the task's
  append-only history, which the assignee and anyone who can see the project read in the task
  panel under **Progress history**.
6. Managers see task status in **Team task progress** on their home and project overview pages.
  These are stored task states, not approvals of milestones or release gates. Changes refresh
  automatically every 30 seconds while visible, and a manual refresh is available.
7. A manager can tick **Requires manager review** on a task. Completing it then reports the work
  as complete and marks it **Pending review**; the project's managers are told in their **Inbox**.
  A manager other than the assignee either **Accepts** it or **Returns it for rework** with a
  reason. Returned work goes back to In Progress at the progress the assignee last reported, and
  the reason appears in the assignee's My Work and in the task's progress history. Reported and
  accepted completion stay separate, and nobody can accept their own work.
8. The **Inbox** tells a person when they are assigned a task or action, when a task in one of
  their projects is reported blocked or complete, and when their completed work is accepted or
  returned. Notifications from a project the person can no longer access are hidden.
9. A manager can assign an action to a project member's account from the action record in the
  project's **Team** tab. The assignee sees it under **My actions** in My Work and can start,
  block or complete it with a short reason.

Requirements Managers (and Project Managers, PMO Analysts and Administrators) can create and edit
requirements, link a requirement to the tasks, test cases and milestones that realise it, remove a
link, and record a test result. Recording a pass requires naming its evidence, and a new result
never keeps the evidence of an earlier one. Each change is audited.

Task and milestone references are generated by the API when omitted. Existing explicit references
remain supported. Assignee selection refuses inactive accounts, accounts outside the project, and
roles without task-update permission. Removing a member with open assigned tasks is refused until
those tasks are reassigned or completed.

## Important safeguards

- Changing a role takes effect immediately because permissions are read from the database on each
  request rather than trusted from the login token.
- Inaccessible projects return “not found” rather than revealing that they exist.
- Updates use row-version checks so one user cannot silently overwrite a newer change.
- Administrators cannot remove their own Administrator role or disable their own account.
- Changes remain subject to the audit trail and governed workflow rules; a role permission does not
  bypass required evidence, confirmation or human review.
