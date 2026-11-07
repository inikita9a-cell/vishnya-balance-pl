from fastapi import Request, HTTPException

COOKIE = "spr_user"


def current_user(request: Request) -> str:
    name = request.cookies.get(COOKIE)
    if not name:
        raise HTTPException(401, "login required")
    return name
