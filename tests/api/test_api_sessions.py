"""Server-side sessions, HttpOnly browser cookies, CSRF, invitations and shared limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.main import create_app
from api.models import InvitationTable
from api.security.permissions import Role
from api.security.sessions import CSRF_HEADER, SESSION_COOKIE, WEB_CLIENT_HEADER
from tests.api.conftest import TEST_ACCOUNTS, TEST_PASSWORD, url

WEB = {WEB_CLIENT_HEADER: "web"}
INVITEE_PASSWORD = "invited-synthetic-7351"


def _login(client: TestClient, role: Role, headers: dict[str, str] | None = None):
    return client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[role][0], "password": TEST_PASSWORD},
        headers=headers or {},
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestServerSessions:
    def test_each_sign_in_is_listed_and_can_be_ended_alone(
        self, anonymous_client: TestClient
    ) -> None:
        first = _login(anonymous_client, Role.ENGINEER).json()["access_token"]
        second = _login(anonymous_client, Role.ENGINEER).json()["access_token"]

        listed = anonymous_client.get(url("/auth/sessions"), headers=_bearer(first)).json()
        assert len(listed) == 2
        other = next(item for item in listed if not item["current"])
        ended = anonymous_client.post(
            url(f"/auth/sessions/{other['id']}/revoke"), headers=_bearer(first)
        )

        assert ended.status_code == 204
        assert anonymous_client.get(url("/auth/me"), headers=_bearer(second)).status_code == 401
        assert anonymous_client.get(url("/auth/me"), headers=_bearer(first)).status_code == 200

    def test_signing_out_ends_the_session(self, anonymous_client: TestClient) -> None:
        token = _login(anonymous_client, Role.ENGINEER).json()["access_token"]

        assert anonymous_client.post(url("/auth/logout"), headers=_bearer(token)).status_code == 204
        assert anonymous_client.get(url("/auth/me"), headers=_bearer(token)).status_code == 401

    def test_other_sessions_can_be_ended_together(self, anonymous_client: TestClient) -> None:
        keep = _login(anonymous_client, Role.ENGINEER).json()["access_token"]
        drop = _login(anonymous_client, Role.ENGINEER).json()["access_token"]

        anonymous_client.post(url("/auth/sessions/revoke-others"), headers=_bearer(keep))

        assert anonymous_client.get(url("/auth/me"), headers=_bearer(drop)).status_code == 401
        assert anonymous_client.get(url("/auth/me"), headers=_bearer(keep)).status_code == 200

    def test_an_administrator_can_end_every_session_for_a_person(
        self, anonymous_client: TestClient, client: TestClient, seeded_engine: Engine
    ) -> None:
        token = _login(anonymous_client, Role.ENGINEER).json()["access_token"]
        engineer_id = anonymous_client.get(url("/auth/me"), headers=_bearer(token)).json()["id"]

        assert client.post(url(f"/admin/users/{engineer_id}/revoke-sessions")).status_code == 204
        assert anonymous_client.get(url("/auth/me"), headers=_bearer(token)).status_code == 401


class TestBrowserCookies:
    def test_the_web_client_never_receives_a_readable_token(
        self, anonymous_client: TestClient
    ) -> None:
        response = _login(anonymous_client, Role.ENGINEER, WEB)

        assert response.status_code == 200
        assert response.json()["access_token"] is None
        assert response.json()["csrf_token"]
        cookie = response.headers["set-cookie"]
        assert f"{SESSION_COOKIE}=" in cookie
        assert "HttpOnly" in cookie
        assert "samesite=lax" in cookie.lower()
        assert "Path=/api" in cookie

    def test_the_cookie_authenticates_reads(self, anonymous_client: TestClient) -> None:
        _login(anonymous_client, Role.ENGINEER, WEB)

        assert anonymous_client.get(url("/auth/me")).status_code == 200
        state = anonymous_client.get(url("/auth/session")).json()
        assert state["csrf_token"] and state["expires_at"]

    def test_a_cookie_write_without_the_csrf_token_is_refused(
        self, anonymous_client: TestClient
    ) -> None:
        csrf = _login(anonymous_client, Role.ENGINEER, WEB).json()["csrf_token"]

        refused = anonymous_client.post(url("/auth/sessions/revoke-others"))
        forged = anonymous_client.post(
            url("/auth/sessions/revoke-others"), headers={CSRF_HEADER: "not-the-token"}
        )
        accepted = anonymous_client.post(
            url("/auth/sessions/revoke-others"), headers={CSRF_HEADER: csrf}
        )

        assert refused.status_code == 403
        assert forged.status_code == 403
        assert accepted.status_code == 204

    def test_signing_out_clears_the_cookie(self, anonymous_client: TestClient) -> None:
        csrf = _login(anonymous_client, Role.ENGINEER, WEB).json()["csrf_token"]

        response = anonymous_client.post(url("/auth/logout"), headers={CSRF_HEADER: csrf})

        assert response.status_code == 204
        assert anonymous_client.get(url("/auth/me")).status_code == 401

    def test_refresh_renews_the_cookie(self, anonymous_client: TestClient) -> None:
        csrf = _login(anonymous_client, Role.ENGINEER, WEB).json()["csrf_token"]

        renewed = anonymous_client.post(url("/auth/refresh"), headers={**WEB, CSRF_HEADER: csrf})

        assert renewed.status_code == 200
        assert renewed.json()["access_token"] is None
        assert SESSION_COOKIE in renewed.headers["set-cookie"]

    def test_changing_the_password_ends_every_session(self, anonymous_client: TestClient) -> None:
        token = _login(anonymous_client, Role.ENGINEER).json()["access_token"]
        other = _login(anonymous_client, Role.ENGINEER).json()["access_token"]

        anonymous_client.post(
            url("/auth/change-password"),
            json={"current_password": TEST_PASSWORD, "new_password": "a-different-password-924"},
            headers=_bearer(token),
        )

        assert anonymous_client.get(url("/auth/me"), headers=_bearer(other)).status_code == 401


class TestInvitations:
    def _invite(self, client: TestClient, email: str, role: str = "project_manager") -> str:
        response = client.post(url("/admin/invitations"), json={"email": email, "role": role})
        assert response.status_code == 201, response.text
        assert response.json()["invitation"]["status"] == "Pending"
        return response.json()["code"]

    def _register(self, client: TestClient, email: str, code: str | None):
        body = {
            "email": email,
            "full_name": "Invited Synthetic Person",
            "password": INVITEE_PASSWORD,
        }
        if code is not None:
            body["invitation_code"] = code
        return client.post(url("/auth/register"), json=body)

    def test_an_invitation_carries_the_chosen_role_once(
        self, client: TestClient, anonymous_client: TestClient
    ) -> None:
        code = self._invite(client, "invitee@test.example.com")

        registered = self._register(anonymous_client, "invitee@test.example.com", code)
        reused = self._register(anonymous_client, "second@test.example.com", code)

        assert registered.status_code == 201, registered.text
        assert registered.json()["user"]["role"] == "project_manager"
        assert reused.status_code == 403
        statuses = {
            item["email"]: item["status"] for item in client.get(url("/admin/invitations")).json()
        }
        assert statuses["invitee@test.example.com"] == "Accepted"

    def test_a_code_works_only_for_its_address(
        self, client: TestClient, anonymous_client: TestClient
    ) -> None:
        code = self._invite(client, "invitee@test.example.com")

        assert self._register(anonymous_client, "other@test.example.com", code).status_code == 403

    def test_an_expired_or_withdrawn_code_is_refused(
        self, client: TestClient, anonymous_client: TestClient, seeded_engine: Engine
    ) -> None:
        expired = self._invite(client, "late@test.example.com")
        withdrawn_code = self._invite(client, "withdrawn@test.example.com")
        with Session(seeded_engine) as session:
            row = session.exec(
                select(InvitationTable).where(InvitationTable.email == "late@test.example.com")
            ).one()
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session.add(row)
            session.commit()
        withdrawn = next(
            item
            for item in client.get(url("/admin/invitations")).json()
            if item["email"] == "withdrawn@test.example.com"
        )
        client.post(url(f"/admin/invitations/{withdrawn['id']}/revoke"))

        assert self._register(anonymous_client, "late@test.example.com", expired).status_code == 403
        assert (
            self._register(
                anonymous_client, "withdrawn@test.example.com", withdrawn_code
            ).status_code
            == 403
        )

    def test_invitation_only_sign_up(
        self, client: TestClient, anonymous_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EPOS_REGISTRATION_REQUIRES_INVITATION", "true")
        code = self._invite(client, "invitee@test.example.com", role="engineer")

        assert self._register(anonymous_client, "walkin@test.example.com", None).status_code == 403
        assert self._register(anonymous_client, "invitee@test.example.com", code).status_code == 201

    def test_only_administrators_invite(self, pm_client: TestClient) -> None:
        response = pm_client.post(
            url("/admin/invitations"), json={"email": "x@test.example.com", "role": "engineer"}
        )

        assert response.status_code == 403


class TestSharedRateLimits:
    def test_failed_sign_ins_are_counted_across_instances(
        self, seeded_engine: Engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EPOS_RATE_LIMIT_STORE", "database")
        wrong = {"email": TEST_ACCOUNTS[Role.ENGINEER][0], "password": "not-the-password-11"}

        statuses = []
        for _ in range(6):
            with TestClient(create_app()) as fresh_instance:
                statuses.append(fresh_instance.post(url("/auth/login"), json=wrong).status_code)

        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
