"""Add workspaces table

Revision ID: add_workspaces_table
Revises: f9111f3f23d1
Create Date: 2024-03-06 10:15:07.186423

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_workspaces_table'
down_revision: Union[str, None] = 'f9111f3f23d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('userid', sa.Integer(), nullable=False),
        sa.Column('wsname', sa.String(), nullable=False),
        sa.Column('filetype', sa.String(), nullable=False),
        sa.Column('filelocation', sa.String(), nullable=True),
        sa.Column('diagramjson', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['userid'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workspaces_id'), 'workspaces', ['id'], unique=False)

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_workspaces_id'), table_name='workspaces')
    op.drop_table('workspaces') 