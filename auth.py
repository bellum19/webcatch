"""
Simple cookie-based auth for Webcatch.
Set WEBCATCH_PASSWORD env var to enable. If not set, everything is open.
"""

import os
import hmac
import hashlib
import time
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

# If this env var is set, auth is required for all non-capture routes
AUTH_PASSWORD = os.getenv("WEBCATCH_PASSWORD", "").strip()
AUTH_ENABLED = bool(AUTH_PASSWORD)
_COOKIE_NAME = "webcatch_session"
_COOKIE_MAX_AGE = 86400 * 30  # 30 days


def _sign(value: str) -> str:
    """Sign a value with HMAC-SHA256 using the auth password."""
    return hmac.new(AUTH_PASSWORD.encode(), value.encode(), hashlib.sha256).hexdigest()


def _make_cookie_value() -> str:
    """Create a signed session cookie value."""
    ts = str(int(time.time()))
    sig = _sign(ts)
    return f"{ts}:{sig}"


def _verify_cookie_value(cookie: str) -> bool:
    """Verify a session cookie hasn't been tampered with and isn't expired."""
    try:
        ts, sig = cookie.split(":", 1)
        expected = _sign(ts)
        if not hmac.compare_digest(sig, expected):
            return False
        age = int(time.time()) - int(ts)
        return age <= _COOKIE_MAX_AGE
    except Exception:
        return False


def require_auth(request: Request):
    """FastAPI dependency: raise 401 if auth is enabled and cookie is missing/invalid."""
    if not AUTH_ENABLED:
        return True
    cookie = request.cookies.get(_COOKIE_NAME, "")
    if cookie and _verify_cookie_value(cookie):
        return True
    raise HTTPException(status_code=401, detail="Authentication required")


def is_authenticated(request: Request) -> bool:
    """Check if the current request is authenticated (for optional checks)."""
    if not AUTH_ENABLED:
        return True
    cookie = request.cookies.get(_COOKIE_NAME, "")
    return bool(cookie and _verify_cookie_value(cookie))


def login_response(password: str) -> Optional[JSONResponse]:
    """Validate password and return a response with the session cookie set."""
    if not AUTH_ENABLED:
        return JSONResponse({"status": "ok", "message": "Auth not configured"})
    if password == AUTH_PASSWORD:
        resp = JSONResponse({"status": "ok", "authenticated": True})
        resp.set_cookie(
            _COOKIE_NAME,
            _make_cookie_value(),
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return resp
    return JSONResponse({"status": "error", "message": "Invalid password"}, status_code=403)


def logout_response() -> JSONResponse:
    """Return a response that clears the session cookie."""
    resp = JSONResponse({"status": "ok", "authenticated": False})
    resp.delete_cookie(_COOKIE_NAME)
    return resp
