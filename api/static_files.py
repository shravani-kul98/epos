"""Serving the built React application from the API process.

The frontend is compiled in CI. When the resulting ``dist`` directory is present, the API also
serves it, so EPOS runs as a single process on one origin. When it is absent the API behaves
exactly as before, which keeps the test suite and API-only deployments unaffected.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
# Build output carries a content hash in its filename, so a stale copy can never be served.
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"

# The interface loads nothing from another origin. Styles allow inline values because the
# component libraries position overlays and charts through style attributes.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)
# Set on the responses this module produces rather than through middleware: top-level middleware
# stops the hosting platform serving the hashed assets from its CDN. The deployment package
# declares the same values for anything the CDN serves.
SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class _HashedAssets(StaticFiles):
    """Static files served with long-lived caching."""

    def file_response(self, *args: object, **kwargs: object) -> Response:
        response = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        response.headers.update(SECURITY_HEADERS)
        response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        return response


def frontend_is_built(dist: Path = FRONTEND_DIST) -> bool:
    """Whether a compiled frontend is available to serve."""
    return (dist / "index.html").is_file()


def _shell_response(index_file: Path) -> Response:
    """The application shell, tagged by its content rather than its file date and size.

    The hosting platform gives every deployed file the same modification time, and a new release
    usually changes only the asset hashes inside the shell, not its length. A date-and-size tag
    would then stay the same across releases and browsers would keep the previous shell.
    """
    content = index_file.read_bytes()
    headers = {
        **SECURITY_HEADERS,
        "Cache-Control": "no-cache",
        "ETag": f'"{hashlib.sha256(content).hexdigest()[:32]}"',
    }
    return Response(content, media_type="text/html", headers=headers)


def mount_frontend(app: FastAPI, api_prefix: str, dist: Path = FRONTEND_DIST) -> bool:
    """Serve the compiled frontend, if one exists.

    Returns ``True`` when the application was mounted. The catch-all route is registered last so
    every API route continues to match first, and requests below the API prefix still return a
    JSON 404 rather than an HTML page.
    """
    if not frontend_is_built(dist):
        return False

    index_file = dist / "index.html"
    api_root = api_prefix.strip("/")

    # Hashed build output is safe to cache; the HTML entry point is not, so it is served separately.
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", _HashedAssets(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> Response:
        """Return a real file when one matches, otherwise the application shell."""
        if full_path.startswith(f"{api_root}/") or full_path == api_root:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

        if full_path:
            candidate = (dist / full_path).resolve()
            # resolve() plus this containment check keeps traversal outside dist impossible.
            if candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate, headers=SECURITY_HEADERS)

        return _shell_response(index_file)

    return True
