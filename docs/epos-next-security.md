# EPOS — Access Control

Authentication and authorisation for the EPOS service layer.

For a concise operational matrix of who can see and change each area, see
[Access by role](access-by-role.md).

## Authentication

Local username/password with JWT bearer tokens.

- **Password storage:** Argon2id via `argon2-cffi`. Passwords are never logged, never returned in
  any response, and never stored in reversible form. New passwords need at least 12 characters and
  5 distinct characters. A sign-in attempt for an unknown address performs the same Argon2 work as
  one for a real account, so response time does not reveal which addresses exist.
- **Token:** short-lived (60 minute) signed JWT carrying the user id, role and expiry. No permissions
  are embedded in the token; they are resolved server-side from the role on every request, so
  revoking or changing a role takes effect immediately rather than at token expiry.
- **Password-bound sessions:** every token carries a keyed fingerprint of the password hash it was
  issued for. Changing a password, or an administrator reset, therefore ends every session issued
  for the old password, including the one that made the change. Tokens without a fingerprint are
  refused.
- **Server-side sessions:** every sign-in creates a session record, and every token names its
  record. A token whose record was ended or has passed its 12-hour limit is refused, so one
  browser or client can be signed out on its own. `GET /auth/sessions` lists a person's live
  sessions; `POST /auth/sessions/{id}/revoke`, `POST /auth/sessions/revoke-others` and
  `POST /auth/logout` end them. An administrator can end every session of an account
  (`POST /admin/users/{id}/revoke-sessions`); disabling an account or changing its password does
  the same.
- **Browser sessions in an HttpOnly cookie:** the interface identifies itself with
  `X-EPOS-Client: web`. It then receives its session as an `HttpOnly`, `SameSite=Lax` cookie
  scoped to `/api` (`Secure` in production), and the response body carries no token, so page
  scripts never hold the credential. Every cookie-authenticated write must echo the session's
  CSRF value in `X-CSRF-Token`; a missing or wrong value is refused with 403. API clients may
  still send a bearer token, which is not ambient and needs no CSRF value.
- **Renewal:** `POST /auth/refresh` re-issues a token for an active session. The original sign-in
  time is carried forward, so a session still ends 12 hours after the password was last entered.
  The interface renews shortly before expiry while the tab is in use.
- **Signing key:** read from `EPOS_SECRET_KEY` or `JWT_SECRET`. In production an absent or short
  (under 32 characters) key stops the application instead of falling back to a default. Local
  development without a key uses a random key generated per process, so every restart ends existing
  sessions and no predictable default exists.
- **Registration:** self-registration always produces the lowest-privilege role. A role can only be
  changed by an Administrator. The client cannot choose its own role. `EPOS_SELF_REGISTRATION=false`
  turns sign-up off, and `EPOS_REGISTRATION_EMAIL_DOMAINS` limits it to listed domains. A duplicate
  address receives a generic refusal that does not name the account; the 409 status itself still
  differs from a success, so full protection against address discovery would need email
  verification, which is not built.
- **Invitations:** an Administrator can invite one address with a chosen role
  (`POST /admin/invitations`). The one-time code is shown once, only its hash is stored, it is
  bound to that address and expires after 7 days; issuing a new code withdraws earlier ones for the
  address. `EPOS_REGISTRATION_REQUIRES_INVITATION=true` makes invitations the only way in. An
  invitation also admits an address that the self-registration policy would refuse.
- **Password reset:** an Administrator can issue a one-time temporary password for another account
  (`POST /admin/users/{id}/reset-password`). It is shown once, never stored in the audit trail, and
  ends that account's sessions. The account is then flagged `password_change_required`: signed in
  with the temporary password it may only read its own profile and session, refresh, sign out and
  change the password. Every other request is refused with 403 and the header
  `X-EPOS-Password: change-required`, and the interface shows only the password change screen.
  Choosing a new password clears the flag and ends every session again. Administrators change
  their own password from their account page.

## Roles

Seven roles, ordered by breadth of authority rather than seniority.

| Role | Purpose |
| --- | --- |
| `executive` | Reads the portfolio and asks questions. Changes nothing. |
| `engineer` | Updates their own assigned work. |
| `engineering_lead` | Updates delivery data for their teams. |
| `requirements_manager` | Owns requirements and raises change requests. Defines test cases, records their results with evidence and maintains trace links. |
| `project_manager` | Runs projects end to end. |
| `pmo_analyst` | Portfolio-wide visibility and project administration. |
| `administrator` | Everything, plus user and workspace management. |

## Permissions

Authorisation is permission-based, not role-name-based. Routes declare the permission they need;
roles are mapped to permissions in one table. This keeps route code readable and makes the security
model reviewable in one place.

| Permission | Executive | Engineer | Eng Lead | Req Manager | PM | PMO | Admin |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `portfolio.read` | yes | yes | yes | yes | yes | yes | yes |
| `project.create` | no | no | no | no | yes | yes | yes |
| `project.update` | no | no | no | no | yes | yes | yes |
| `project.delete` | no | no | no | no | no | no | yes |
| `project_members.manage` | no | no | no | no | yes | yes | yes |
| `work.update` | no | yes | yes | no | yes | yes | yes |
| `work.manage` | no | no | yes | no | yes | yes | yes |
| `action.manage` | no | no | yes | no | yes | yes | yes |
| `risk.manage` | no | no | yes | no | yes | yes | yes |
| `issue.manage` | no | no | yes | no | yes | yes | yes |
| `assumption.manage` | no | no | yes | yes | yes | yes | yes |
| `requirement.manage` | no | no | no | yes | yes | yes | yes |
| `change.create` | no | no | no | yes | yes | yes | yes |
| `change.decide` | no | no | no | no | yes | yes | yes |
| `scenario.run` | no | no | yes | yes | yes | yes | yes |
| `report.read` | yes | no | yes | yes | yes | yes | yes |
| `copilot.ask` | yes | yes | yes | yes | yes | yes | yes |
| `user.manage` | no | no | no | no | no | no | yes |
| `workspace.admin` | no | no | no | no | no | no | yes |

`work.update` allows editing a task's own progress, status and blocker flag, and adding progress
notes to it. `work.manage` allows
creating and deleting work and reassigning it to other people.

## Enforcement

Every mutating route depends on `require(permission)`. There is no route that mutates data without
a permission check, and a test asserts that by walking the generated OpenAPI document. Project
access is checked before a submitted identifier is looked up, so a caller outside a project cannot
learn which identifiers exist in it. Identifiers are unique across every record type.

Failure modes are distinguished so the interface can respond correctly:

| Condition | Status |
| --- | --- |
| No, malformed, expired or revoked token | 401 |
| Valid token, insufficient permission | 403 |
| Valid token, disabled account | 403 |
| Authorised, record absent or outside the caller's projects | 404 |
| Governance refusal (a decided change request, a decided decision, a frozen assumption, an account that still owns open work, a review of one's own completed task) | 409 |
| Too many requests | 429, with `Retry-After` |

Read endpoints require authentication but not a specific permission, except reports.

## Request limits

Counted in the database shared by every application instance in production
(`EPOS_RATE_LIMIT_STORE=database`, the production default), and in each instance's memory
elsewhere. Keys are stored only as hashes. `EPOS_RATE_LIMITS=false` turns them off.

| Limit | Allowance |
| --- | --- |
| Failed sign-ins per account | 5 in 15 minutes; a successful sign-in clears the count |
| Failed sign-ins per network address | 20 in 15 minutes |
| Registrations per network address | 10 per hour |
| Assistant questions and scenario explanations per account | 30 in 5 minutes |

The network address is the peer the process sees. Behind a proxy that hides client addresses, the
per-address limits apply to all clients together.

## Browser protections

The compiled interface and its assets are served with a Content Security Policy that allows only
the application's own origin (inline styles excepted, for component positioning), plus
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a strict referrer policy and a
permissions policy. They are set on the responses themselves rather than through middleware.

## What is deliberately not built

No password reset email, no email verification, no multi-factor authentication, no separate
refresh-token rotation, no OAuth or directory integration. Invitation codes are handed over by the
administrator rather than emailed. These are noted so nobody mistakes the current state for a
complete identity solution.
