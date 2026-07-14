#!/usr/bin/env python3
"""Restore a backup archive produced by scripts/backup.py.

Usage: python scripts/restore.py /app/data/storage/exports/backups/backup-<ts>.tar.gz

This overwrites the current database and local storage tree. It is
destructive by design (restore implies replacing current state) — run it only
when you intend to discard current local data.
"""
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/app/data/storage"))


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    archive_path = Path(sys.argv[1])
    if not archive_path.exists():
        print(f"[restore] Archive not found: {archive_path}", file=sys.stderr)
        return 1

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("[restore] DATABASE_URL is not set; cannot restore the database.", file=sys.stderr)
        return 1

    if sys.stdin.isatty():
        print(f"[restore] This will REPLACE the current database and data/storage with the")
        print(f"[restore] contents of {archive_path}. Current data will be lost.")
        confirmation = input("[restore] Type YES to continue: ")
        if confirmation != "YES":
            print("[restore] Aborted.")
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(tmp_path)

        psql_url = database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
        dump_file = tmp_path / "database.sql"
        if dump_file.exists():
            result = subprocess.run(
                # -v ON_ERROR_STOP=1: without this, psql -f prints each
                # statement error to stderr but keeps going and still exits
                # 0 -- a restore that silently left half the schema
                # unrestored while reporting success is a worse failure mode
                # than one that visibly stops and says so.
                ["psql", "-v", "ON_ERROR_STOP=1", psql_url, "-f", str(dump_file)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"[restore] psql restore failed: {result.stderr}", file=sys.stderr)
                return 1

        storage_dump = tmp_path / "storage"
        if storage_dump.exists():
            for child in storage_dump.iterdir():
                target = STORAGE_ROOT / child.name
                # dirs_exist_ok=True merges into an already-existing target
                # directory (e.g. data/storage/projects, created by the
                # Dockerfile on every fresh container) instead of nesting a
                # second copy inside it -- shutil.copytree(child, target)
                # without that flag raises FileExistsError; the previous
                # `cp -R child target` silently did the wrong thing instead
                # of erroring, copying into target/<child.name>/ and leaving
                # every restored file at a path the app would never look for.
                if child.is_dir():
                    shutil.copytree(child, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, target)

    print(f"[restore] Restored from {archive_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
