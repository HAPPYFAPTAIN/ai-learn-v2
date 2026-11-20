"""Enforce project chapter codes; abort on duplicates, never rewrite user data."""
from alembic import op
from sqlalchemy import text
revision = '0010_unique_chapter_code'
down_revision = '0009_runtime_timeouts'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    # Even a non-BYPASSRLS schema owner can inspect every tenant safely by
    # setting the same transaction-local tenant context used by the app.
    tenants = bind.execute(text('SELECT id FROM tenant')).scalars().all()
    for tenant in tenants:
        bind.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {'tenant': str(tenant)})
        duplicate = bind.execute(text('SELECT 1 FROM le_knode GROUP BY project_id, code HAVING count(*) > 1 LIMIT 1')).first()
        if duplicate:
            raise RuntimeError('发现重复章节编号；请先通知负责人处理，本迁移不会自动删除或改写数据')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_le_knode_project_code ON le_knode (tenant_id, project_id, code)')

def downgrade():
    op.drop_index('uq_le_knode_project_code', table_name='le_knode')
