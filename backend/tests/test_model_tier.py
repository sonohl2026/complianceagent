import logging

from app.services.quick_scan.model_tier import is_tier_split_active, warn_if_tier_split_inactive


def test_active_when_both_dedicated_settings_set():
    settings = {
        "openrouter_extraction_model": "anthropic/claude-haiku-4.5",
        "openrouter_synthesis_model": "anthropic/claude-sonnet-4-6",
        "openrouter_model": "anthropic/claude-haiku-4.5",
    }
    assert is_tier_split_active(settings) is True


def test_inactive_when_extraction_model_unset():
    settings = {
        "openrouter_extraction_model": "",
        "openrouter_synthesis_model": "anthropic/claude-sonnet-4-6",
        "openrouter_model": "anthropic/claude-haiku-4.5",
    }
    assert is_tier_split_active(settings) is False


def test_inactive_when_synthesis_model_unset():
    settings = {
        "openrouter_extraction_model": "anthropic/claude-haiku-4.5",
        "openrouter_synthesis_model": "",
        "openrouter_model": "anthropic/claude-haiku-4.5",
    }
    assert is_tier_split_active(settings) is False


def test_inactive_when_both_unset():
    settings = {"openrouter_extraction_model": "", "openrouter_synthesis_model": "", "openrouter_model": "anthropic/claude-haiku-4.5"}
    assert is_tier_split_active(settings) is False


def test_warn_logs_when_inactive(caplog):
    settings = {"openrouter_extraction_model": "", "openrouter_synthesis_model": "", "openrouter_model": "anthropic/claude-haiku-4.5"}
    with caplog.at_level(logging.WARNING):
        warn_if_tier_split_inactive(settings, context="test context")
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    message = caplog.records[0].getMessage()
    assert "test context" in message
    assert "anthropic/claude-haiku-4.5" in message  # names the actual fallback model, not just "something"


def test_warn_is_silent_when_active(caplog):
    settings = {
        "openrouter_extraction_model": "anthropic/claude-haiku-4.5",
        "openrouter_synthesis_model": "anthropic/claude-sonnet-4-6",
        "openrouter_model": "anthropic/claude-haiku-4.5",
    }
    with caplog.at_level(logging.WARNING):
        warn_if_tier_split_inactive(settings, context="test context")
    assert len(caplog.records) == 0
