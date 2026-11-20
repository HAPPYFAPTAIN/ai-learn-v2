"""Tenant-owned model catalog and selection for personal or official sources."""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from learn_api.auth import Principal, get_principal
from learn_api.deps import get_tenant_id
from learn_api.errors import ApiError
from learn_api.schemas import ModelCatalogOut, ModelSelectionOut
from learn_core.db.engine import session_scope
from learn_core.learning.model_settings import selected_model, save_model
from learn_core.llm.gateway import GatewayClient, GatewayError
from learn_core.tenancy.context import tenant_context
from learn_core.config import get_settings
from learn_core.llm import providers

router = APIRouter(prefix='/models', tags=['models'])


class ModelSelection(BaseModel):
    model: str = Field(min_length=1, max_length=128)


def _gateway():
    return GatewayClient()


def _catalog(principal: Principal):
    if get_settings().model_source == 'personal':
        with session_scope() as session:
            return providers.catalog(session)
    try:
        with _gateway() as gateway:
            return gateway.list_models(end_user=principal.official_user_id)
    except GatewayError as exc:
        # A product-key/upstream failure must not log the browser out or expose its body.
        if exc.status == 402:
            raise ApiError('INSUFFICIENT_CREDITS', '可用积分不足，请到官网补充后继续') from exc
        raise ApiError('GATEWAY_UNAVAILABLE', str(exc)) from exc


@router.get('', response_model=ModelCatalogOut)
def models(response: Response, principal: Principal = Depends(get_principal), tenant_id=Depends(get_tenant_id)):
    response.headers['Cache-Control'] = 'no-store'
    # Close the DB transaction before waiting for the gateway.
    with tenant_context(tenant_id), session_scope() as session:
        selected = selected_model(session)
    with tenant_context(tenant_id):
        items = _catalog(principal)
    personal = get_settings().model_source == 'personal'
    # Retain legacy preferences in the DB for rollback, but never present them
    # as imported personal credentials or automatically use them in this mode.
    if personal and not selected.startswith('personal.'):
        selected = ''
    return {'items': items, 'selectedModel': selected,
            'selectedAvailable': any(m['id'] == selected for m in items),
            'source': get_settings().model_source,
            'providerImportEnabled': personal and providers.enabled()}


@router.patch('/selection', response_model=ModelSelectionOut)
def choose(payload: ModelSelection, response: Response,
           principal: Principal = Depends(get_principal), tenant_id=Depends(get_tenant_id)):
    response.headers['Cache-Control'] = 'no-store'
    # Revalidate on each save: a client can forge options or keep an outdated list.
    with tenant_context(tenant_id):
        if get_settings().model_source == 'personal':
            with session_scope() as session:
                providers.lock_connections(session)
                if payload.model not in {m['id'] for m in providers.catalog(session)}:
                    raise ApiError('INVALID_ARGUMENT', '所选模型当前不可用，请刷新模型列表')
                save_model(session, model=payload.model)
            return {'selectedModel': payload.model}
        if payload.model not in {m['id'] for m in _catalog(principal)}:
            raise ApiError('INVALID_ARGUMENT', '所选模型当前不可用，请刷新模型列表')
        with session_scope() as session:
            save_model(session, model=payload.model)
    return {'selectedModel': payload.model}
