"""Report every API route that does not require an authenticated user.

Run: python scripts/audit_route_auth.py
Exits non-zero when a non-public route is reachable without authentication.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.routing import APIRoute  # noqa: E402

from api.main import API_PREFIX, create_app  # noqa: E402
from api.security.dependencies import get_current_user  # noqa: E402

# Routes that are public by design: sign-in, self-registration and the readiness probes.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        f"{API_PREFIX}/auth/register",
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/ready",
    }
)


def _requires_authentication(route: APIRoute) -> bool:
    """True when resolving the route runs the authentication dependency."""
    return any(
        dependency.call is get_current_user
        for dependency in route.dependant.dependencies + [route.dependant]
        if dependency.call is not None
    ) or _nested_uses_auth(route)


def _nested_uses_auth(route: APIRoute) -> bool:
    """Walk the dependency tree, since permissions wrap the authentication dependency."""
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        if dependency.call is get_current_user:
            return True
        pending.extend(dependency.dependencies)
    return False


def _collect_api_routes(routes: list, prefix: str = "") -> list[tuple[str, APIRoute]]:
    """Return every reachable API route with its fully resolved path.

    Recent FastAPI versions keep an included router as a single object rather than copying its
    routes onto the application, so the inclusion is followed explicitly here. Without this the
    audit would only ever see the handful of routes declared directly on the application.
    """
    collected: list[tuple[str, APIRoute]] = []
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            collected.extend(_collect_api_routes(list(included.routes), prefix + API_PREFIX))
            continue
        if isinstance(route, APIRoute):
            collected.append((prefix + route.path, route))
    return collected


def main() -> int:
    app = create_app()
    discovered = _collect_api_routes(list(app.routes))

    # Guard against silent under-reporting: discovery must match the published API surface.
    found_paths = {path for path, _ in discovered if path.startswith(API_PREFIX)}
    documented_paths = {path for path in app.openapi()["paths"] if path.startswith(API_PREFIX)}
    if found_paths != documented_paths:
        print("ROUTE DISCOVERY INCOMPLETE:")
        for path in sorted(documented_paths - found_paths):
            print(f"  documented but not inspected: {path}")
        for path in sorted(found_paths - documented_paths):
            print(f"  inspected but not documented: {path}")
        return 1

    unprotected: list[str] = []
    for path, route in discovered:
        if not path.startswith(API_PREFIX) or path in PUBLIC_PATHS:
            continue
        if not _requires_authentication(route):
            unprotected.append(f"{sorted(route.methods)} {path}")

    if unprotected:
        print("UNPROTECTED ROUTES:")
        for entry in sorted(unprotected):
            print(f"  {entry}")
        return 1

    print(f"All {len(discovered)} API routes inspected; non-public routes require authentication.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
