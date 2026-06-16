from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, status

from backend.app.core.config import settings
from backend.app.core.errors import ApiError, ErrorCode


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "ledger:read",
        "ledger:write",
        "webhooks:read",
        "webhooks:write",
        "webhooks:replay",
        "fraud:read",
        "audit:read",
        "slo:read",
    },
    "analyst": {
        "ledger:read",
        "webhooks:read",
        "fraud:read",
        "slo:read",
    },
    "integration": {
        "ledger:write",
        "webhooks:write",
        "webhooks:replay",
        "slo:read",
    },
}


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str

    @property
    def permissions(self) -> set[str]:
        return ROLE_PERMISSIONS.get(self.role, set())


def get_principal(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> Principal:
    if not x_api_key or x_api_key not in settings.api_key_roles:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ErrorCode.auth_missing,
            message="A valid X-API-Key header is required.",
        )
    role, actor = settings.api_key_roles[x_api_key]
    return Principal(actor=actor, role=role)


def require_permission(permission: str) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if permission not in principal.permissions:
            raise ApiError(
                status_code=status.HTTP_403_FORBIDDEN,
                code=ErrorCode.forbidden,
                message=f"Role '{principal.role}' cannot perform '{permission}'.",
                details={"required_permission": permission},
            )
        return principal

    return dependency
