from fastapi import Request, HTTPException, status
from auth import get_session_user

SESSION_COOKIE = "lexora_session"

def get_user(request: Request):
    token = request.cookies.get("lexora_session")

    if not token:
        return None

    return get_session_user(token)

async def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)

    user = get_session_user(token)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    return user
