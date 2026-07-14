#!/usr/bin/env python3
"""Placeholder for local admin/user bootstrap.

The MVP is explicitly single-user with no authentication (see docs/security.md
and build spec §4.2 "Features that may be deferred"). This script is a hook
point for the multi-user milestone; it intentionally does nothing yet.
"""
import sys


def main() -> int:
    print("[create_admin] Multi-user auth is deferred past the MVP; nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
