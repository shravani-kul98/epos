"""Server-allocated references, test-case and allocation upkeep, and the attention rule."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.security.permissions import Role
from src.scoring_rules import ATTENTION_ALERT_SEVERITIES, ATTENTION_HEALTH_BANDS
from tests.api.conftest import url

_REFERENCE_CASES: tuple[tuple[str, str, dict[str, object]], ...] = (
    (
        "/issues",
        "issue_id",
        {
            "title": "Qualification fixture unavailable",
            "description": "The validation team cannot complete the planned test sequence.",
            "severity": "High",
            "owner": "Test Lead",
            "raised_date": "2026-08-27",
        },
    ),
    (
        "/assumptions",
        "assumption_id",
        {
            "assumption_text": "The synthetic supplier fixture arrives before validation.",
            "owner": "Test Project Manager",
            "validation_due_date": "2026-09-01",
            "impact_if_false": "Validation would move beyond the planned gate.",
        },
    ),
    (
        "/work-packages",
        "work_package_id",
        {
            "work_package_name": "Synthetic release evidence package",
            "description": "Groups synthetic engineering evidence for release review.",
            "owner": "Test Lead",
            "accountable_owner": "Test Project Manager",
            "status": "Planned",
            "priority": "High",
        },
    ),
    (
        "/dependencies",
        "dependency_id",
        {
            "predecessor_type": "Task",
            "predecessor_id": "T-2002",
            "successor_type": "Milestone",
            "successor_id": "M-203",
            "dependency_name": "Engineering evidence before release gate",
            "relationship_type": "Finish-to-Start",
            "lag_days": 2,
            "status": "On Track",
            "delay_days": 0,
            "criticality": "High",
        },
    ),
    (
        "/actions",
        "action_id",
        {
            "action_description": "Confirm the synthetic supplier tooling date",
            "owner": "Test Lead",
            "due_date": "2026-09-15",
            "priority": "High",
        },
    ),
    (
        "/change-requests",
        "change_request_id",
        {
            "requirement_id": "REQ-2001",
            "change_description": "Tighten the synthetic response-time requirement",
            "reason": "Customer review feedback",
            "priority": "High",
            "requested_date": "2026-08-01",
        },
    ),
)


# A second record must differ where the register forbids duplicates, such as a dependency edge.
_SECOND_OVERRIDES: dict[str, dict[str, object]] = {"/dependencies": {"successor_id": "M-202"}}


class TestServerAllocatedReferences:
    def test_every_register_allocates_a_readable_project_reference(
        self, client: TestClient
    ) -> None:
        for path, id_field, fields in _REFERENCE_CASES:
            first = client.post(url(path), json={"project_id": "P-002", **fields})
            second = client.post(
                url(path),
                json={"project_id": "P-002", **fields, **_SECOND_OVERRIDES.get(path, {})},
            )

            assert first.status_code == 201, (path, first.text)
            assert second.status_code == 201, (path, second.text)
            first_id, second_id = first.json()[id_field], second.json()[id_field]
            prefix = first_id.rsplit("-", 1)[0]
            assert prefix.endswith("-P-002"), first_id
            assert second_id == f"{prefix}-{int(first_id.rsplit('-', 1)[1]) + 1:03d}"

    def test_a_supplied_reference_is_kept_and_a_duplicate_rejected(
        self, client: TestClient
    ) -> None:
        _, _, fields = _REFERENCE_CASES[0]
        payload = {"issue_id": "ISS-950", "project_id": "P-002", **fields}

        assert client.post(url("/issues"), json=payload).json()["issue_id"] == "ISS-950"
        assert client.post(url("/issues"), json=payload).status_code == 409

    def test_a_gate_gets_the_next_free_sequence_and_its_parts_get_references(
        self, client: TestClient
    ) -> None:
        gate = {
            "project_id": "P-002",
            "milestone_id": "M-202",
            "gate_name": "Synthetic design review",
            "planned_review_date": "2026-10-15",
            "owner": "Test Project Manager",
        }
        first = client.post(url("/gates"), json=gate).json()
        second = client.post(url("/gates"), json=gate).json()

        assert first["gate_id"].startswith("G-P-002-")
        assert second["sequence"] == first["sequence"] + 1
        criterion = client.post(
            url(f"/gates/{first['gate_id']}/criteria"),
            json={
                "criterion_type": "Exit",
                "criterion_name": "Synthetic evidence accepted",
                "description": "The synthetic verification record has been reviewed.",
                "is_mandatory": True,
                "evidence_required": False,
            },
        )
        assert criterion.status_code == 201, criterion.text
        assert criterion.json()["criterion_id"].startswith("GC-P-002-")

    def test_a_deliverable_reference_is_allocated_under_its_package(
        self, client: TestClient
    ) -> None:
        _, _, package_fields = _REFERENCE_CASES[2]
        package = client.post(url("/work-packages"), json={"project_id": "P-002", **package_fields})
        deliverable = client.post(
            url("/deliverables"),
            json={
                "project_id": "P-002",
                "work_package_id": package.json()["work_package_id"],
                "deliverable_name": "Synthetic verification package",
                "description": "A synthetic, reviewable engineering outcome.",
                "owner": "Test Engineer",
                "accountable_owner": "Test Lead",
                "status": "Planned",
                "priority": "High",
                "acceptance_criteria": "All synthetic checks have recorded evidence.",
            },
        )

        assert deliverable.status_code == 201, deliverable.text
        assert deliverable.json()["deliverable_id"].startswith("DL-P-002-")


class TestTestCases:
    def test_a_new_test_case_starts_not_run_and_is_audited(
        self, requirements_client: TestClient, client: TestClient
    ) -> None:
        response = requirements_client.post(
            url("/test-cases"),
            json={"project_id": "P-002", "test_case_name": "Synthetic boot timing check"},
        )

        assert response.status_code == 201, response.text
        created = response.json()
        assert created["test_case_id"].startswith("TC-P-002-")
        assert created["status"] == "Not Run"
        assert created["verification_evidence"] is None
        assert created["row_version"] == 1
        listed = client.get(url("/projects/P-002/test-cases")).json()
        assert created["test_case_id"] in {row["test_case_id"] for row in listed}
        events = client.get(url("/activity"), params={"project_id": "P-002"}).json()
        assert any(event["entity_id"] == created["test_case_id"] for event in events)

    def test_a_status_cannot_be_supplied_on_creation(self, requirements_client: TestClient) -> None:
        response = requirements_client.post(
            url("/test-cases"),
            json={"project_id": "P-002", "test_case_name": "Forged pass", "status": "Passed"},
        )

        assert response.status_code == 422

    def test_creation_is_permissioned_and_project_scoped(
        self, engineer_client: TestClient, requirements_client: TestClient
    ) -> None:
        payload = {"project_id": "P-002", "test_case_name": "Synthetic check"}

        assert engineer_client.post(url("/test-cases"), json=payload).status_code == 403
        outside = payload | {"project_id": "P-011"}
        assert requirements_client.post(url("/test-cases"), json=outside).status_code == 404


class TestResources:
    _ALLOCATION = {
        "project_id": "P-002",
        "resource_name": "Test Engineer",
        "allocated_hours": 44,
        "capacity_hours": 40,
        "week_start_date": "2026-09-07",
    }

    def test_an_allocation_reports_engine_utilisation(self, pm_client: TestClient) -> None:
        response = pm_client.post(url("/resources"), json=self._ALLOCATION)

        assert response.status_code == 201, response.text
        created = response.json()
        assert created["resource_id"].startswith("RES-P-002-")
        assert created["utilisation_percent"] == 110.0
        assert created["is_overallocated"] is True

    def test_an_allocation_is_corrected_with_its_version(self, pm_client: TestClient) -> None:
        created = pm_client.post(url("/resources"), json=self._ALLOCATION).json()
        path = url(f"/resources/{created['resource_id']}")

        stale = pm_client.patch(path, json={"allocated_hours": 30, "row_version": 99})
        corrected = pm_client.patch(
            path, json={"allocated_hours": 30, "row_version": created["row_version"]}
        )

        assert stale.status_code == 409
        assert corrected.status_code == 200
        assert corrected.json()["is_overallocated"] is False
        withdrawn = pm_client.delete(path, params={"row_version": corrected.json()["row_version"]})
        assert withdrawn.status_code == 204
        listed = pm_client.get(url("/projects/P-002/resources")).json()
        assert created["resource_id"] not in {row["resource_id"] for row in listed}

    def test_allocations_are_permissioned_validated_and_scoped(
        self, engineer_client: TestClient, pm_client: TestClient
    ) -> None:
        assert engineer_client.post(url("/resources"), json=self._ALLOCATION).status_code == 403
        no_capacity = self._ALLOCATION | {"capacity_hours": 0}
        assert pm_client.post(url("/resources"), json=no_capacity).status_code == 422
        outside = self._ALLOCATION | {"project_id": "P-011"}
        assert pm_client.post(url("/resources"), json=outside).status_code == 404


class TestAttention:
    def test_the_flag_follows_the_shared_rule(self, client: TestClient) -> None:
        dashboard = client.get(url("/analytics/portfolio")).json()
        alerts = client.get(url("/analytics/alerts")).json()

        for project in dashboard["projects"]:
            severities = {
                alert["severity"]
                for alert in alerts
                if alert["project_id"] == project["project_id"]
            }
            expected = project["health_band"] in ATTENTION_HEALTH_BANDS or bool(
                severities & ATTENTION_ALERT_SEVERITIES
            )
            assert project["needs_attention"] is expected, project["project_id"]

    def test_the_filter_selects_assessed_projects_by_the_flag(self, client: TestClient) -> None:
        everything = client.get(url("/analytics/portfolio")).json()["projects"]
        flagged = client.get(url("/analytics/portfolio"), params={"needs_attention": True}).json()
        calm = client.get(url("/analytics/portfolio"), params={"needs_attention": False}).json()

        assessed = [row for row in everything if row["assessment"]["is_assessed"]]
        assert {row["project_id"] for row in flagged["projects"]} == {
            row["project_id"] for row in assessed if row["needs_attention"]
        }
        assert {row["project_id"] for row in calm["projects"]} == {
            row["project_id"] for row in assessed if not row["needs_attention"]
        }
        assert flagged["projects"], "the starter workspace has projects needing attention"


class TestPasswordChangeAfterReset:
    def test_a_temporary_password_admits_only_a_password_change(
        self, client: TestClient, anonymous_client: TestClient, users: dict[Role, str]
    ) -> None:
        engineer = next(
            row
            for row in client.get(url("/admin/users")).json()
            if row["email"] == users[Role.ENGINEER]
        )
        temporary = client.post(url(f"/admin/users/{engineer['id']}/reset-password")).json()[
            "temporary_password"
        ]
        signed_in = anonymous_client.post(
            url("/auth/login"), json={"email": users[Role.ENGINEER], "password": temporary}
        )
        headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}

        me = anonymous_client.get(url("/auth/me"), headers=headers)
        blocked = anonymous_client.get(url("/projects"), headers=headers)

        assert me.status_code == 200
        assert me.json()["password_change_required"] is True
        assert blocked.status_code == 403
        assert blocked.headers["X-EPOS-Password"] == "change-required"

        new_password = "a-chosen-passphrase-for-tests-91"
        changed = anonymous_client.post(
            url("/auth/change-password"),
            json={"current_password": temporary, "new_password": new_password},
            headers=headers,
        )
        assert changed.status_code == 204

        again = anonymous_client.post(
            url("/auth/login"), json={"email": users[Role.ENGINEER], "password": new_password}
        )
        fresh = {"Authorization": f"Bearer {again.json()['access_token']}"}
        assert anonymous_client.get(url("/projects"), headers=fresh).status_code == 200
        assert (
            anonymous_client.get(url("/auth/me"), headers=fresh).json()["password_change_required"]
            is False
        )

    def test_an_ordinary_account_is_not_asked_to_change(self, engineer_client: TestClient) -> None:
        assert engineer_client.get(url("/auth/me")).json()["password_change_required"] is False
        assert engineer_client.get(url("/projects")).status_code == 200
