"""Authentication tests: registration, sign-in, tokens and account safety."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from api.models import UserTable
from api.security.permissions import DEFAULT_ROLE, Permission, Role, has_permission
from api.security.tokens import (
    MIN_PASSWORD_LENGTH,
    TOKEN_ALGORITHM,
    create_access_token,
    hash_password,
    signing_key,
    verify_password,
)
from tests.api.conftest import TEST_ACCOUNTS, TEST_PASSWORD, url

NEW_ACCOUNT = {
    "email": "newcomer@test.example.com",
    "full_name": "New Comer",
    "password": "a-strong-enough-password-42",
    "job_title": "Systems Engineer",
}


# ------------------------------------------------------------------ password hashing
def test_password_hash_is_not_the_password() -> None:
    digest = hash_password("a-strong-enough-password-42")
    assert "a-strong-enough-password-42" not in digest
    assert digest.startswith("$argon2")


def test_password_verifies_against_its_hash() -> None:
    digest = hash_password("a-strong-enough-password-42")
    assert verify_password("a-strong-enough-password-42", digest)
    assert not verify_password("a-strong-enough-password-43", digest)


def test_hashing_is_salted() -> None:
    """Two identical passwords must not produce the same stored value."""
    assert hash_password("a-strong-enough-password-42") != hash_password(
        "a-strong-enough-password-42"
    )


def test_verification_of_a_corrupt_hash_fails_safely() -> None:
    assert verify_password("anything", "not-a-real-hash") is False


# ------------------------------------------------------------------ registration
def test_registration_returns_a_token_and_user(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT)
    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "newcomer@test.example.com"


def test_registration_always_uses_the_lowest_privilege_role(
    anonymous_client: TestClient,
) -> None:
    body = anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT).json()
    assert body["user"]["role"] == DEFAULT_ROLE.value


def test_registration_cannot_choose_its_own_role(anonymous_client: TestClient) -> None:
    """A client must not be able to escalate itself by sending a role."""
    payload = NEW_ACCOUNT | {"role": "administrator"}
    assert anonymous_client.post(url("/auth/register"), json=payload).status_code == 422


def test_registration_never_returns_a_password_hash(anonymous_client: TestClient) -> None:
    body = anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT).text
    assert "password_hash" not in body
    assert "argon2" not in body


def test_duplicate_registration_is_refused(anonymous_client: TestClient) -> None:
    anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT)
    assert anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT).status_code == 409


def test_registration_is_case_insensitive_on_email(anonymous_client: TestClient) -> None:
    anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT)
    upper = NEW_ACCOUNT | {"email": "NEWCOMER@TEST.EXAMPLE.COM"}
    assert anonymous_client.post(url("/auth/register"), json=upper).status_code == 409


def test_short_password_is_refused(anonymous_client: TestClient) -> None:
    payload = NEW_ACCOUNT | {"password": "a" * (MIN_PASSWORD_LENGTH - 1)}
    assert anonymous_client.post(url("/auth/register"), json=payload).status_code == 422


def test_password_without_variety_is_refused(anonymous_client: TestClient) -> None:
    payload = NEW_ACCOUNT | {"password": "aaaaaaaaaaaaaaaa"}
    assert anonymous_client.post(url("/auth/register"), json=payload).status_code == 422


def test_malformed_email_is_refused(anonymous_client: TestClient) -> None:
    payload = NEW_ACCOUNT | {"email": "not-an-email"}
    assert anonymous_client.post(url("/auth/register"), json=payload).status_code == 422


# ------------------------------------------------------------------ sign in
def test_correct_credentials_return_a_token(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[Role.PROJECT_MANAGER][0], "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_wrong_password_is_rejected(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[Role.PROJECT_MANAGER][0], "password": "wrong-password-here"},
    )
    assert response.status_code == 401


def test_unknown_and_wrong_password_give_the_same_answer(anonymous_client: TestClient) -> None:
    """The endpoint must not reveal which email addresses are registered."""
    unknown = anonymous_client.post(
        url("/auth/login"), json={"email": "nobody@test.example.com", "password": "whatever-1234"}
    )
    wrong = anonymous_client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[Role.ENGINEER][0], "password": "whatever-1234"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_sign_in_records_the_time(anonymous_client: TestClient, engine) -> None:
    anonymous_client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[Role.ENGINEER][0], "password": TEST_PASSWORD},
    )
    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == TEST_ACCOUNTS[Role.ENGINEER][0])
        ).one()
    assert user.last_login_at is not None


def test_disabled_account_cannot_sign_in(
    anonymous_client: TestClient, client: TestClient, engine
) -> None:
    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == TEST_ACCOUNTS[Role.ENGINEER][0])
        ).one()
    client.patch(url(f"/admin/users/{user.id}/active"), json={"is_active": False})

    response = anonymous_client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[Role.ENGINEER][0], "password": TEST_PASSWORD},
    )
    assert response.status_code == 403


# ------------------------------------------------------------------ tokens
def test_protected_route_requires_a_token(anonymous_client: TestClient) -> None:
    assert anonymous_client.get(url("/projects")).status_code == 401


def test_garbage_token_is_rejected(anonymous_client: TestClient) -> None:
    anonymous_client.headers["Authorization"] = "Bearer not-a-token"
    assert anonymous_client.get(url("/projects")).status_code == 401


def test_token_signed_with_another_key_is_rejected(anonymous_client: TestClient) -> None:
    forged = jwt.encode(
        {"sub": "1", "email": "x@test.example.com", "role": "administrator", "exp": 9999999999},
        "an-attackers-key",
        algorithm=TOKEN_ALGORITHM,
    )
    anonymous_client.headers["Authorization"] = f"Bearer {forged}"
    assert anonymous_client.get(url("/projects")).status_code == 401


def test_expired_token_is_rejected(anonymous_client: TestClient) -> None:
    expired = jwt.encode(
        {
            "sub": "1",
            "email": "x@test.example.com",
            "role": "administrator",
            "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
        },
        signing_key(),
        algorithm=TOKEN_ALGORITHM,
    )
    anonymous_client.headers["Authorization"] = f"Bearer {expired}"
    assert anonymous_client.get(url("/projects")).status_code == 401


def test_unsigned_token_is_rejected(anonymous_client: TestClient) -> None:
    """The ``none`` algorithm must never be accepted."""
    unsigned = jwt.encode(
        {"sub": "1", "email": "x@test.example.com", "role": "administrator", "exp": 9999999999},
        key="",
        algorithm="none",
    )
    anonymous_client.headers["Authorization"] = f"Bearer {unsigned}"
    assert anonymous_client.get(url("/projects")).status_code == 401


def test_token_for_a_deleted_user_is_rejected(anonymous_client: TestClient) -> None:
    orphan = create_access_token(9999, "ghost@test.example.com", Role.ADMINISTRATOR)
    anonymous_client.headers["Authorization"] = f"Bearer {orphan}"
    assert anonymous_client.get(url("/projects")).status_code == 401


def test_role_change_takes_effect_without_a_new_token(
    engineer_client: TestClient, client: TestClient, engine
) -> None:
    """Permissions are resolved from the stored record, not from the token."""
    assert engineer_client.get(url("/admin/users")).status_code == 403

    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == TEST_ACCOUNTS[Role.ENGINEER][0])
        ).one()
    client.patch(url(f"/admin/users/{user.id}/role"), json={"role": "administrator"})

    assert engineer_client.get(url("/admin/users")).status_code == 200


def test_disabling_an_account_invalidates_its_session(
    engineer_client: TestClient, client: TestClient, engine
) -> None:
    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == TEST_ACCOUNTS[Role.ENGINEER][0])
        ).one()
    client.patch(url(f"/admin/users/{user.id}/active"), json={"is_active": False})

    # Disabling ends the account's sessions; signing in again is refused as disabled.
    assert engineer_client.get(url("/projects")).status_code == 401


# ------------------------------------------------------------------ current user
def test_me_returns_the_signed_in_user(pm_client: TestClient) -> None:
    body = pm_client.get(url("/auth/me")).json()
    assert body["email"] == TEST_ACCOUNTS[Role.PROJECT_MANAGER][0]
    assert body["role"] == Role.PROJECT_MANAGER.value


def test_me_advertises_the_permissions_the_interface_should_adapt_to(
    executive_client: TestClient,
) -> None:
    body = executive_client.get(url("/auth/me")).json()
    assert Permission.PORTFOLIO_READ.value in body["permissions"]
    assert Permission.PROJECT_CREATE.value not in body["permissions"]


def test_me_uses_a_readable_role_name(pm_client: TestClient) -> None:
    assert pm_client.get(url("/auth/me")).json()["role_label"] == "Project Manager"


def test_me_never_exposes_the_password_hash(pm_client: TestClient) -> None:
    assert "password_hash" not in pm_client.get(url("/auth/me")).text


# ------------------------------------------------------------------ password change
def test_password_can_be_changed(pm_client: TestClient, anonymous_client: TestClient) -> None:
    response = pm_client.post(
        url("/auth/change-password"),
        json={"current_password": TEST_PASSWORD, "new_password": "another-good-password-77"},
    )
    assert response.status_code == 204

    signed_in = anonymous_client.post(
        url("/auth/login"),
        json={
            "email": TEST_ACCOUNTS[Role.PROJECT_MANAGER][0],
            "password": "another-good-password-77",
        },
    )
    assert signed_in.status_code == 200


def test_password_change_requires_the_current_password(pm_client: TestClient) -> None:
    response = pm_client.post(
        url("/auth/change-password"),
        json={"current_password": "not-the-password", "new_password": "another-good-password-77"},
    )
    assert response.status_code == 403


def test_password_change_enforces_the_minimum_length(pm_client: TestClient) -> None:
    response = pm_client.post(
        url("/auth/change-password"),
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ permission table
@pytest.mark.parametrize("role", list(Role))
def test_every_role_can_read_the_portfolio(role: Role) -> None:
    assert has_permission(role, Permission.PORTFOLIO_READ)


@pytest.mark.parametrize("role", [r for r in Role if r is not Role.ADMINISTRATOR])
def test_only_the_administrator_manages_users(role: Role) -> None:
    assert not has_permission(role, Permission.USER_MANAGE)


def test_the_executive_cannot_change_anything() -> None:
    forbidden = {
        Permission.PROJECT_CREATE,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MEMBERS_MANAGE,
        Permission.WORK_UPDATE,
        Permission.WORK_MANAGE,
        Permission.ACTION_MANAGE,
        Permission.RISK_MANAGE,
        Permission.ISSUE_MANAGE,
        Permission.ASSUMPTION_MANAGE,
        Permission.REQUIREMENT_MANAGE,
        Permission.CHANGE_CREATE,
        Permission.CHANGE_DECIDE,
    }
    for permission in forbidden:
        assert not has_permission(Role.EXECUTIVE, permission), permission


def test_only_the_administrator_deletes_projects() -> None:
    for role in Role:
        expected = role is Role.ADMINISTRATOR
        assert has_permission(role, Permission.PROJECT_DELETE) is expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [(role, role in {Role.PROJECT_MANAGER, Role.PMO_ANALYST, Role.ADMINISTRATOR}) for role in Role],
)
def test_only_governance_roles_manage_project_members(role: Role, expected: bool) -> None:
    assert has_permission(role, Permission.PROJECT_MEMBERS_MANAGE) is expected


@pytest.mark.parametrize(
    ("permission", "roles"),
    [
        (
            Permission.ACTION_MANAGE,
            {Role.ENGINEERING_LEAD, Role.PROJECT_MANAGER, Role.PMO_ANALYST, Role.ADMINISTRATOR},
        ),
        (
            Permission.ISSUE_MANAGE,
            {Role.ENGINEERING_LEAD, Role.PROJECT_MANAGER, Role.PMO_ANALYST, Role.ADMINISTRATOR},
        ),
        (
            Permission.ASSUMPTION_MANAGE,
            {
                Role.ENGINEERING_LEAD,
                Role.REQUIREMENTS_MANAGER,
                Role.PROJECT_MANAGER,
                Role.PMO_ANALYST,
                Role.ADMINISTRATOR,
            },
        ),
    ],
)
def test_governance_register_permissions_are_explicit(
    permission: Permission, roles: set[Role]
) -> None:
    for role in Role:
        assert has_permission(role, permission) is (role in roles)
