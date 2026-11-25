from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationPrincipal, ApplicationRefreshSession
from app.platform.auth.session_epoch import read_session_epoch


def revoke_all_refresh_sessions(session: Session, principal: ApplicationPrincipal) -> None:
    session.execute(
        update(ApplicationRefreshSession)
        .where(
            ApplicationRefreshSession.principal_id == principal.id,
            ApplicationRefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


def refresh_session_epoch_for_principal(principal: ApplicationPrincipal) -> int:
    return read_session_epoch(principal)