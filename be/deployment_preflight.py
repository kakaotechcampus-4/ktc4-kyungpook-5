"""Check the selected database without printing credentials or changing schema."""

import os

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("Deployment preflight: DATABASE_URL is missing.")
        return 1
    try:
        expected = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        try:
            with engine.connect() as connection:
                current = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
                vector = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
        finally:
            engine.dispose()
        if set(current) != set(expected) or not vector:
            print("Deployment preflight: database revision or vector extension does not match.")
            return 1
    except Exception:
        # Driver errors can contain credentials, host names or SQL parameters.
        print("Deployment preflight: cannot verify database connectivity and schema.")
        return 1
    print("Deployment preflight: database connection, schema revision and vector extension verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
