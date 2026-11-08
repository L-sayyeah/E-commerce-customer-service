"""Verify configured bearer credentials and expose a server-owned identity."""

import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Principal, settings

_bearer = HTTPBearer(auto_error=False)


def require_principal(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credential is not None:
        digest = hashlib.sha256(credential.credentials.encode("utf-8")).hexdigest()
        principal = settings.auth_token_digests.get(digest)
        if principal is not None:
            return principal
    raise HTTPException(
        status_code=401,
        detail="Valid bearer credentials required",
        headers={"WWW-Authenticate": "Bearer"},
    )


CurrentPrincipal = Annotated[Principal, Depends(require_principal)]


def require_admin(principal: CurrentPrincipal) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return principal


AdminPrincipal = Annotated[Principal, Depends(require_admin)]
