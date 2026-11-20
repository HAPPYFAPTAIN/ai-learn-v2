"""Persistent model preference shared by every learning feature; no credentials."""
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from learn_core.db.models import TenantSetting
from learn_core.tenancy.context import current_tenant


def selected_model(session: Session) -> str:
    setting = session.get(TenantSetting, current_tenant())
    return setting.chat_model if setting else ''


def require_model(session: Session) -> str:
    from learn_core.config import get_settings
    from learn_core.llm.providers import ModelNotConfigured, resolve
    model = selected_model(session)
    if not model:
        raise ModelNotConfigured(code='MODEL_NOT_SELECTED', message='请先到「模型设置」选择主模型')
    if get_settings().model_source == 'personal' or model.startswith('personal.'):
        resolve(session, model)
    return model


def save_model(session: Session, *, model: str) -> None:
    from sqlalchemy import func
    stmt = insert(TenantSetting).values(tenant_id=current_tenant(), chat_model=model)
    session.execute(stmt.on_conflict_do_update(
        index_elements=[TenantSetting.tenant_id],
        set_={'chat_model': model, 'updated_at': func.now()},
    ))
