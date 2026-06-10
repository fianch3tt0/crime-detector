"""Initial schema with PostGIS crimes table.

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "crimes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("raw_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("offense", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("beat", sa.Text(), nullable=True),
        sa.Column("division", sa.Text(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("uix_crimes_raw_id", "crimes", ["raw_id"], unique=True)
    op.create_index("ix_crimes_occurred_at", "crimes", ["occurred_at"])
    op.create_index(
        "ix_crimes_geometry", "crimes", ["geometry"], postgresql_using="gist"
    )
    op.create_index(
        "ix_crimes_category_time", "crimes", ["category", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_crimes_category_time", table_name="crimes")
    op.drop_index("ix_crimes_geometry", table_name="crimes")
    op.drop_index("ix_crimes_occurred_at", table_name="crimes")
    op.drop_index("uix_crimes_raw_id", table_name="crimes")
    op.drop_table("crimes")
