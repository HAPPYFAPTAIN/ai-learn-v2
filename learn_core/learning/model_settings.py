"""Persistent model preference shared by every learning feature; no credentials."""
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from learn_core.db.models import TenantSetting
from learn_core.tenancy.context import current_tenant


def selected_model(session: Session) -> str:
    setting = session.get(TenantSetting, current_tenant())
    return setting.chat_model if setting else ''


def save_model(session: Session, *, model: str) -> None:
    from sqlalchemy import func
    stmt = insert(TenantSetting).values(tenant_id=current_tenant(), chat_model=model)
    session.execute(stmt.on_conflict_do_update(
        index_elements=[TenantSetting.tenant_id],
        set_={'chat_model': model, 'updated_at': func.now()},
    ))
