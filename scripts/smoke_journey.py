"""End-to-end smoke journey against a throwaway file database.

Exercises real application startup (Alembic migrations), authentication, project-scoped
authorization and the governed Gate lifecycle through the ASGI app. Uses a temporary database and
a locally generated password, so no real workspace data and no committed credential is involved.

Run: python scripts/smoke_journey.py
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TEMP_DIR = tempfile.mkdtemp(prefix="epos_smoke_")
_DB_PATH = Path(_TEMP_DIR) / "smoke.db"
os.environ["EPOS_DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from api.database import get_engine  # noqa: E402
from api.main import API_PREFIX, create_app  # noqa: E402
from api.security.permissions import Role  # noqa: E402
from api.seed import seed_database  # noqa: E402
from api.services import user_service  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record one journey assertion without aborting the run."""
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES.append(f"{label}: {detail}")
    print(f"  [{status}] {label}{'' if condition else f' -> {detail}'}")


def main() -> int:
    print(f"Temporary database: {_DB_PATH}")
    written = seed_database()
    print(f"Seeded collections: {len(written)}")

    email = "smoke.admin@epos.example.com"
    password = f"Smoke-{secrets.token_urlsafe(16)}"
    with Session(get_engine()) as session:
        user_service.register(
            session,
            email=email,
            full_name="Smoke Administrator",
            password=password,
            job_title="Release Auditor",
            role=Role.ADMINISTRATOR,
        )

    with TestClient(create_app()) as client:
        print("\nJourney 1: authentication")
        anonymous = client.get(f"{API_PREFIX}/projects")
        check(
            "unauthenticated read is refused",
            anonymous.status_code == 401,
            str(anonymous.status_code),
        )

        login = client.post(f"{API_PREFIX}/auth/login", json={"email": email, "password": password})
        check("sign-in succeeds", login.status_code == 200, login.text[:120])
        if login.status_code != 200:
            return 1
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        bad = client.get(f"{API_PREFIX}/projects", headers={"Authorization": "Bearer not-a-token"})
        check("forged token is refused", bad.status_code == 401, str(bad.status_code))

        print("\nJourney 2: portfolio and deterministic analytics")
        projects = client.get(f"{API_PREFIX}/projects")
        check("projects load", projects.status_code == 200, str(projects.status_code))
        project_id = projects.json()[0]["project_id"] if projects.json() else ""
        dashboard = client.get(f"{API_PREFIX}/analytics/projects/{project_id}")
        check("project dashboard loads", dashboard.status_code == 200, str(dashboard.status_code))
        if dashboard.status_code == 200:
            health = dashboard.json()["health"]
            check("health cites evidence", bool(health["source_ids"]), "no source ids")
            check(
                "health score is bounded",
                0 <= health["score"] <= 100,
                str(health["score"]),
            )

        print("\nJourney 3: governed Gate lifecycle")
        milestones = client.get(f"{API_PREFIX}/projects/{project_id}/milestones").json()
        gate_payload = {
            "gate_id": "G-SMOKE-1",
            "project_id": project_id,
            "milestone_id": milestones[0]["milestone_id"] if milestones else None,
            "gate_name": "Smoke readiness Gate",
            "sequence": 991,
            "planned_review_date": "2026-12-01",
            "owner": "Smoke Administrator",
            "applicable_baseline": "Smoke baseline",
        }
        created = client.post(f"{API_PREFIX}/gates", json=gate_payload)
        check("gate is created", created.status_code == 201, created.text[:160])
        if created.status_code != 201:
            return 1

        empty = client.get(f"{API_PREFIX}/gates/G-SMOKE-1/readiness").json()
        check("gate with no criteria is Not Ready", empty["state"] == "Not Ready", empty["state"])
        check(
            "no criteria means no percentage", empty["percentage"] is None, str(empty["percentage"])
        )

        version = client.get(f"{API_PREFIX}/gates/G-SMOKE-1").json()["row_version"]
        prep = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/transition",
            json={
                "target_status": "Preparing",
                "rationale": "Begin smoke preparation.",
                "row_version": version,
            },
        )
        check("gate moves to Preparing", prep.status_code == 200, prep.text[:160])

        criterion = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/criteria",
            json={
                "criterion_id": "GC-SMOKE-1",
                "criterion_type": "Exit",
                "criterion_name": "Smoke evidence accepted",
                "description": "Synthetic smoke criterion.",
                "is_mandatory": True,
                "evidence_required": True,
            },
        )
        check("criterion is configured", criterion.status_code == 201, criterion.text[:160])

        no_evidence = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/criteria/GC-SMOKE-1/assessment",
            json={
                "target_status": "Met",
                "rationale": "Claimed without evidence.",
                "row_version": criterion.json()["row_version"],
            },
        )
        check(
            "Met without required evidence is refused",
            no_evidence.status_code == 409,
            str(no_evidence.status_code),
        )

        blocked = client.get(f"{API_PREFIX}/gates/G-SMOKE-1/readiness").json()
        check("mandatory gap blocks readiness", blocked["state"] == "Not Ready", blocked["state"])
        check(
            "blocker cites the criterion",
            any("GC-SMOKE-1" in finding["source_ids"] for finding in blocked["blockers"]),
            str(blocked["blockers"]),
        )

        assessed = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/criteria/GC-SMOKE-1/assessment",
            json={
                "target_status": "Met",
                "rationale": "Smoke evidence reviewed.",
                "evidence_reference": "EV-SMOKE-1",
                "row_version": criterion.json()["row_version"],
            },
        )
        check(
            "criterion is assessed with evidence", assessed.status_code == 200, assessed.text[:160]
        )

        ready = client.get(f"{API_PREFIX}/gates/G-SMOKE-1/readiness").json()
        check(
            "readiness becomes Ready for Review",
            ready["state"] == "Ready for Review",
            ready["state"],
        )
        check("percentage is complete", ready["percentage"] == 100, str(ready["percentage"]))

        version = client.get(f"{API_PREFIX}/gates/G-SMOKE-1").json()["row_version"]
        client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/transition",
            json={
                "target_status": "Ready for Review",
                "rationale": "Ready.",
                "row_version": version,
            },
        )
        version = client.get(f"{API_PREFIX}/gates/G-SMOKE-1").json()["row_version"]
        client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/transition",
            json={
                "target_status": "In Review",
                "rationale": "Start review.",
                "row_version": version,
            },
        )

        version = client.get(f"{API_PREFIX}/gates/G-SMOKE-1").json()["row_version"]
        premature = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/transition",
            json={
                "target_status": "Passed",
                "rationale": "Attempt pass without review.",
                "row_version": version,
            },
        )
        check(
            "passing without a human review is refused",
            premature.status_code == 409,
            str(premature.status_code),
        )

        review = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/reviews",
            json={"review_id": "GR-SMOKE-1", "outcome": "Approved", "rationale": "Smoke approval."},
        )
        check("human review is recorded", review.status_code == 201, review.text[:160])
        check(
            "reviewer is server-assigned",
            review.json().get("reviewer") == "Smoke Administrator",
            review.text[:120],
        )

        version = client.get(f"{API_PREFIX}/gates/G-SMOKE-1").json()["row_version"]
        passed = client.post(
            f"{API_PREFIX}/gates/G-SMOKE-1/transition",
            json={
                "target_status": "Passed",
                "rationale": "Approved at smoke review.",
                "row_version": version,
            },
        )
        check("gate passes after approval", passed.status_code == 200, passed.text[:160])
        check(
            "recorded result is Passed", passed.json().get("result") == "Passed", passed.text[:120]
        )

        print("\nJourney 4: audit trail and immutability")
        events = client.get(
            f"{API_PREFIX}/activity", params={"project_id": project_id, "limit": 50}
        ).json()
        summaries = " ".join(event["summary"] for event in events)
        check("gate creation is audited", "G-SMOKE-1" in summaries, "no gate event")
        check(
            "actor is named", all(event.get("actor_name") for event in events[:5]), "missing actor"
        )
        patched = client.patch(f"{API_PREFIX}/gates/G-SMOKE-1/reviews/GR-SMOKE-1", json={})
        check(
            "reviews expose no update route", patched.status_code == 405, str(patched.status_code)
        )

        print("\nJourney 5: Ask EPOS grounding")
        ask = client.post(
            f"{API_PREFIX}/copilot/ask", json={"question": "which projects need attention?"}
        )
        check(
            "copilot answers without Azure configured", ask.status_code == 200, str(ask.status_code)
        )
        if ask.status_code == 200:
            body = ask.json()
            # Since calculated fallbacks stopped claiming AI review, only AI narration declares
            # it; an answer without that flag must say it is calculated facts, not AI output.
            check(
                "an answer without human review is labelled as calculated facts",
                body.get("human_review_required") is True
                or any("not an AI explanation" in warning for warning in body.get("warnings", [])),
                str(body.get("warnings")),
            )
            source_ids = body.get("source_ids", [])
            # Source IDs cover records and deterministic alert identifiers alike; the binding
            # grounding rule (IDs must exist in the evidence package) is enforced in ask_epos.
            check(
                "every cited source id is a non-empty string",
                all(isinstance(sid, str) and sid.strip() for sid in source_ids),
                str(source_ids[:5]),
            )
            check("the answer cites evidence", bool(source_ids), "no source ids returned")
            check(
                "no business record was mutated",
                client.get(f"{API_PREFIX}/gates/G-SMOKE-1").json()["status"] == "Passed",
                "gate changed during a question",
            )

        print("\nJourney 6: Ask EPOS honours restrictions")
        tech = client.post(
            f"{API_PREFIX}/copilot/ask", json={"question": "list down only tech projects"}
        )
        check("a restricted list is answered", tech.status_code == 200, str(tech.status_code))
        if tech.status_code == 200:
            body = tech.json()
            check("the applied filter is shown", bool(body.get("applied_filters")), tech.text[:160])
            listed = body.get("source_ids", [])
            check(
                "only matching projects are listed",
                0 < len(listed) < len(projects.json()),
                str(listed),
            )
        unknown = client.post(
            f"{API_PREFIX}/copilot/ask", json={"question": "list only blockchain projects"}
        )
        check(
            "an unrecorded restriction is reported instead of widened",
            unknown.status_code == 200
            and bool(unknown.json().get("unapplied_filters"))
            and not unknown.json().get("source_ids"),
            unknown.text[:160],
        )

        print("\nJourney 7: sign-out ends the session")
        signed_out = client.post(f"{API_PREFIX}/auth/logout")
        check("sign-out succeeds", signed_out.status_code == 204, str(signed_out.status_code))
        reused = client.get(f"{API_PREFIX}/projects")
        check("the signed-out token is refused", reused.status_code == 401, str(reused.status_code))

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"SMOKE JOURNEY FAILED: {len(FAILURES)} check(s)")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("SMOKE JOURNEY PASSED: every check succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
