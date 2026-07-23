"""Whether the two-tier model split (spec §2: cheap Stage 1 extraction,
strong Stage 3 synthesis) is actually in effect.

Found silently collapsed for at least a week on this deployment: both
openrouter_extraction_model and openrouter_synthesis_model were empty, so
pipeline.py's own fallback ("... or model") sent Stage 1 AND Stage 3 to the
same single openrouter_model -- with nothing anywhere (logs, /metrics, UI)
surfacing that fact. Every benchmark and diagnostic result produced during
that time was synthesis running on the extraction-tier model, not the
strong tier the design and every calibration decision assumed. See status
report §2/§7. This module makes that state impossible to miss again.
"""

import logging

logger = logging.getLogger(__name__)


def is_tier_split_active(settings: dict) -> bool:
    """True only if BOTH dedicated settings are explicitly populated -- if
    either is empty, pipeline.py's fallback sends that stage to the shared
    openrouter_model, and the split is not actually happening regardless of
    what the architecture supports."""
    return bool(settings.get("openrouter_extraction_model")) and bool(settings.get("openrouter_synthesis_model"))


def warn_if_tier_split_inactive(settings: dict, *, context: str) -> None:
    """context is a short label (e.g. "startup", "quick_scan run") so the log
    line says where the check fired, not just that it failed. Deliberately
    loud (WARNING, not INFO/DEBUG) and repeated on every call site rather
    than logged once and silenced -- the whole point is that this must never
    again be the kind of thing you have to go looking for."""
    if is_tier_split_active(settings):
        return
    fallback_model = settings.get("openrouter_model") or "(none configured)"
    logger.warning(
        "Model tier split is NOT active (%s): openrouter_extraction_model and/or "
        "openrouter_synthesis_model is unset in Settings, so Stage 1 and Stage 3 "
        "both fall back to openrouter_model (%s). This silently collapses the "
        "cheap-extraction/strong-synthesis design onto a single model tier -- "
        "set both settings explicitly in Settings if that split is intended.",
        context, fallback_model,
    )
