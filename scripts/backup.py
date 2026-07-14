#!/usr/bin/env python3
"""Back up the Postgres database and local storage tree to a single archive.

Writes data/storage/exports/backups/<timestamp>.tar.gz containing a
`pg_dump` of the database plus the contents of data/storage (excluding the
backups directory itself). Restore with scripts/restore.py.
"""
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/app/data/storage"))
BACKUP_DIR = STORAGE_ROOT / "exports" / "backups"


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("[backup] DATABASE_URL is not set; cannot pg_dump.", file=sys.stderr)
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump_path = BACKUP_DIR / f"db-{timestamp}.sql"
    archive_path = BACKUP_DIR / f"backup-{timestamp}.tar.gz"

    pg_dump_url = database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    result = subprocess.run(
        [
            "pg_dump",
            pg_dump_url,
            # --clean --if-exists: emit DROP ... IF EXISTS before each CREATE,
            # so restoring into an already-migrated database (the normal case
            # -- alembic upgrade head has already run) replaces cleanly
            # instead of erroring on "relation already exists" for every
            # table, or worse, silently duplicating rows in tables that
            # happened to already exist.
            "--clean",
            "--if-exists",
            # --no-owner/--no-privileges: the dump is portable across any
            # target role name rather than pinned to whatever role happened
            # to own the objects at dump time -- there is only ever one role
            # in this deployment today, but restoring role-agnostic dumps is
            # the standard, low-risk default.
            "--no-owner",
            "--no-privileges",
            "-f",
            str(dump_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[backup] pg_dump failed: {result.stderr}", file=sys.stderr)
        return 1

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(dump_path, arcname="database.sql")
        for child in STORAGE_ROOT.iterdir():
            if child.name == "exports":
                continue
            tar.add(child, arcname=f"storage/{child.name}")

    dump_path.unlink(missing_ok=True)
    print(f"[backup] Wrote {archive_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
