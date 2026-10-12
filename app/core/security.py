import base64
import secrets

from fastapi import HTTPException, Request


def require_api_access(request: Request, settings) -> None:
    token = getattr(settings, "api_token", "")
    user = getattr(settings, "admin_user", "")
    password = getattr(settings, "admin_password", "")

    if not token and not (user and password):
        return

    supplied = request.headers.get("X-NVM-Token", "")
    if token and supplied and secrets.compare_digest(supplied, token):
        return

    auth = request.headers.get("Authorization", "")
    if user and password and auth.startswith("Basic "):
        try:
            raw = base64.b64decode(auth[6:], validate=True).decode("utf-8")
            got_user, got_password = raw.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            got_user = got_password = ""
        if secrets.compare_digest(got_user, user) and secrets.compare_digest(got_password, password):
            return

    raise HTTPException(
        status_code=401,
        detail="authentication_required",
        headers={"WWW-Authenticate": 'Basic realm="NVM"'},
    )
