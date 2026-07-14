"""Test-session setup.

PROMPTS_ROOT defaults to /app/prompts, which is only valid inside the api
container (docker-compose mounts ./prompts there). When running tests
directly on the host (as this sandbox does, with no Docker available),
point it at the real repo-relative prompts/ directory instead.

This must run at module import time (not inside a fixture): pytest imports
conftest.py before collecting sibling test modules, but a fixture only runs
once the test session starts executing -- by which point other modules may
already have called the lru_cache'd get_settings() with the wrong default.
"""

import os
from pathlib import Path

_REPO_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
if _REPO_PROMPTS_DIR.exists():
    os.environ.setdefault("PROMPTS_ROOT", str(_REPO_PROMPTS_DIR))
