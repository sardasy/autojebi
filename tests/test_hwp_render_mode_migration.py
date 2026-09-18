from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.util import load_python_file


def test_render_mode_migration_preserves_old_templates_and_downgrades():
    migration = load_python_file(
        str(Path(__file__).resolve().parents[1] / "alembic" / "versions"),
        "0015_hwp_render_mode.py",
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE hwp_templates (id VARCHAR PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO hwp_templates (id) VALUES ('existing')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert conn.execute(sa.text("SELECT render_mode FROM hwp_templates")).scalar() == "fields"
        conn.execute(sa.text("INSERT INTO hwp_templates VALUES ('layout', 'proposal_layout_v1')"))
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("INSERT INTO hwp_templates VALUES ('invalid', 'script')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert [col["name"] for col in sa.inspect(conn).get_columns("hwp_templates")] == ["id"]
        assert conn.execute(sa.text("SELECT count(*) FROM hwp_templates")).scalar() == 2
