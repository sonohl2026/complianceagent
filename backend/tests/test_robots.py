from app.services.crawling.robots import build_robots_parser, crawl_delay, is_allowed

ROBOTS_TXT = """
User-agent: *
Disallow: /admin/
Disallow: /internal/
Crawl-delay: 2

User-agent: MedTechComplianceAgent
Disallow: /no-agent-specific/
"""


def test_disallowed_path_is_blocked_for_generic_agent():
    # Per robots.txt semantics, a matching agent-specific group (see below)
    # replaces the wildcard group entirely for that agent -- so this checks
    # the "*" group's own disallow rule, using an agent with no dedicated group.
    parser = build_robots_parser(ROBOTS_TXT, "https://example.com/robots.txt")
    assert is_allowed(parser, "SomeOtherBot", "https://example.com/admin/settings") is False


def test_agent_specific_group_overrides_wildcard_group_entirely():
    # MedTechComplianceAgent has its own group, so the wildcard's
    # "Disallow: /admin/" does not apply to it -- only its own rules do.
    parser = build_robots_parser(ROBOTS_TXT, "https://example.com/robots.txt")
    assert is_allowed(parser, "MedTechComplianceAgent", "https://example.com/admin/settings") is True


def test_allowed_path_passes():
    parser = build_robots_parser(ROBOTS_TXT, "https://example.com/robots.txt")
    assert is_allowed(parser, "MedTechComplianceAgent", "https://example.com/products") is True


def test_agent_specific_rule_applies():
    parser = build_robots_parser(ROBOTS_TXT, "https://example.com/robots.txt")
    assert (
        is_allowed(parser, "MedTechComplianceAgent", "https://example.com/no-agent-specific/x")
        is False
    )


def test_missing_robots_txt_defaults_to_allow_all():
    parser = build_robots_parser(None, "https://example.com/robots.txt")
    assert is_allowed(parser, "MedTechComplianceAgent", "https://example.com/anything") is True


def test_crawl_delay_is_parsed():
    parser = build_robots_parser(ROBOTS_TXT, "https://example.com/robots.txt")
    assert crawl_delay(parser, "*") == 2
