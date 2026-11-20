"""Bound idle runtime transactions (run with a role allowed to alter learn_app)."""
from alembic import op
revision = '0009_runtime_timeouts'
down_revision = '0008_model_providers'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER ROLE learn_app SET idle_in_transaction_session_timeout = '5min'")

def downgrade():
    op.execute('ALTER ROLE learn_app RESET idle_in_transaction_session_timeout')
