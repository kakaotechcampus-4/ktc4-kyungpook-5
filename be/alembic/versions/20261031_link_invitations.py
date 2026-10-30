"""Allow invitations without an email recipient for copyable links."""
from alembic import op

revision = "20261031_link_invitations"
down_revision = "20261030_action_version"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("invitations", "email", nullable=True)


def downgrade():
    op.execute("UPDATE invitations SET email = '' WHERE email IS NULL")
    op.alter_column("invitations", "email", nullable=False)
