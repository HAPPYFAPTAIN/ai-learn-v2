"""Explicit personal credential imports, using existing official authentication."""
from time import monotonic
from datetime import timedelta
from fastapi import APIRouter, Depends, Response
from learn_api.deps import get_tenant_id
from learn_api.errors import ApiError
from learn_api.schemas import ProviderListOut, ProviderCreatedOut
from learn_core.config import get_settings
from learn_core.db.engine import session_scope
from learn_core.llm import providers as service
from learn_core.llm.lease import acquire, release, LeaseUnavailable
from learn_core.tenancy.context import tenant_context

router = APIRouter(prefix='/model-providers', tags=['models'])


def personal_mode():
    if get_settings().model_source != 'personal':
        raise service.ProviderError('INVALID_ARGUMENT', '当前部署使用官网模型，个人 Key 导入未启用。')


@router.get('', response_model=ProviderListOut)
def providers(tenant_id=Depends(get_tenant_id)):
    personal_mode()
    with tenant_context(tenant_id), session_scope() as session:
        return {'enabled': service.enabled(), 'connections': service.connections(session)}


@router.post('', response_model=ProviderCreatedOut)
def add(payload: service.ProviderInput, tenant_id=Depends(get_tenant_id)):
    personal_mode()
    started = monotonic()
    with tenant_context(tenant_id):
        # Reuse the existing interactive limit and close the DB transaction
        # before waiting on the provider. Importing never makes a paid call.
        try:
            with session_scope() as session:
                holder = acquire(session, tenant_id=tenant_id, lane='interactive', ttl=timedelta(seconds=120))
        except LeaseUnavailable:
            raise ApiError('TENANT_BUSY', '正在验证供应商或回答问题，请稍后再试。', retry_after_seconds=5) from None
        try:
            service.verify(payload)
            with session_scope() as session:
                connection = service.save(session, payload=payload)
        finally:
            with session_scope() as session:
                release(session, tenant_id=tenant_id, lane='interactive', holder=holder)
    return {'connection': connection, 'verifiedMs': round((monotonic() - started) * 1000)}


@router.delete('/{provider_id}', status_code=204)
def remove(provider_id: str, tenant_id=Depends(get_tenant_id)):
    personal_mode()
    with tenant_context(tenant_id), session_scope() as session:
        service.remove(session, provider_id)
    return Response(status_code=204)
