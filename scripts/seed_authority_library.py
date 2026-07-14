#!/usr/bin/env python3
"""Seed the authority library with a starter set of official-source records.

Intentionally a no-op: the SourceDocument model and the
POST /api/v1/authority/documents upload path exist as of Milestone 2, but
this script deliberately does NOT fabricate authority-document rows without
real backing content (build spec §28 rule 2: "Do not replace core
functionality with mock data"). Fetching real current official-source
documents (FDA, CMS, eCFR, etc.) requires either the Milestone 4 crawler or a
human uploading a real, properly licensed/official document through the
Authority Library UI — both are legitimate paths that already work; this
script is a placeholder for a future "seed from a vetted domain allowlist"
convenience once Milestone 4 lands (build spec §19.2).
"""
import sys


def main() -> int:
    print(
        "[seed_authority_library] No fabricated authority documents are seeded. "
        "Upload real official/licensed sources via the Authority Library page, "
        "or wait for Milestone 4's crawler-based seeding convenience."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
