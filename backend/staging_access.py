"""Application-wide HTTPS Basic authentication for a small staging allowlist."""
import base64
import hashlib
import hmac
import json
import os
import re
from urllib.parse import urlsplit
from fastapi.responses import JSONResponse

def settings():
    users = json.loads(os.environ["STAGING_USERS_JSON"])
    origin = os.environ["APP_BASE_URL"].rstrip("/")
    url = urlsplit(origin)
    if url.scheme != "https" or not url.netloc or url.path or url.username or url.query or url.fragment:
        raise ValueError("HTTPS origin required")
    if not isinstance(users, dict) or not users:
        raise ValueError("Allowlist required")
    for name, encoded in users.items():
        if not re.fullmatch(r"[a-zA-Z0-9_.@-]{1,64}", name):
            raise ValueError("Invalid identity")
        salt, digest = encoded.split(":")
        if len(bytes.fromhex(salt)) != 16 or len(bytes.fromhex(digest)) != 32:
            raise ValueError("Invalid password hash")
    return users, origin

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()

async def protect(request, call_next):
    if request.url.path == "/healthz" and request.method in ("GET", "HEAD"):
        return await call_next(request)
    try:
        users, origin = settings()
    except (KeyError, ValueError, TypeError, AttributeError):
        return JSONResponse({"detail": "Staging access is not configured"}, status_code=503)
    # Never trust forwarded identity headers or demo cookies.
    name = ""
    valid = False
    try:
        scheme, token = request.headers.get("authorization", "").split(" ", 1)
        if scheme.lower() != "basic" or len(token) > 2048:
            raise ValueError()
        name, password = base64.b64decode(token, validate=True).decode().split(":", 1)
        stored = users.get(name, "00" * 16 + ":" + "00" * 32)
        salt, expected = stored.split(":")
        valid = hmac.compare_digest(password_hash(password, salt), expected) and name in users
    except (ValueError, UnicodeError):
        pass
    if not valid:
        return JSONResponse({"detail": "Authentication required"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="StrategyLab", charset="UTF-8"'})
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin") != origin:
            return JSONResponse({"detail": "Same-origin request required"}, status_code=403)
    request.state.verified_user = name
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response
