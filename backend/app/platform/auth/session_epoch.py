from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationPrincipal


def read_session_epoch(principal: ApplicationPrincipal) -> int:
    raw = principal.metadata_json.get("session_epoch", 0)
    return int(raw) if isinstance(raw, int) else 0


def bump_session_epoch(session: Session, principal: ApplicationPrincipal) -> int:
    from app.platform.auth.refresh_epoch import revoke_all_refresh_sessions

    epoch = read_session_epoch(principal) + 1
    principal.metadata_json = {**principal.metadata_json, "session_epoch": epoch}
    session.add(principal)
    session.flush()
    revoke_all_refresh_sessions(session, principal)
    return epoch