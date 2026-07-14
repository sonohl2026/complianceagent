from app.services.crawling.crawler import CrawlSettings, should_fetch


def _settings(**overrides) -> CrawlSettings:
    defaults = dict(start_url="https://sonohl.com/")
    defaults.update(overrides)
    return CrawlSettings(**defaults)


def test_offsite_link_is_rejected():
    assert should_fetch("https://competitor.com/", "sonohl.com", _settings()) is False


def test_onsite_link_is_accepted():
    assert should_fetch("https://sonohl.com/about", "sonohl.com", _settings()) is True


def test_subdomain_rejected_unless_follow_subdomains_set():
    assert should_fetch("https://blog.sonohl.com/", "sonohl.com", _settings()) is False
    assert (
        should_fetch("https://blog.sonohl.com/", "sonohl.com", _settings(follow_subdomains=True))
        is True
    )


def test_exclusion_pattern_blocks_matching_url():
    settings = _settings(exclusion_patterns=["/legal/"])
    assert should_fetch("https://sonohl.com/legal/terms", "sonohl.com", settings) is False
    assert should_fetch("https://sonohl.com/product", "sonohl.com", settings) is True


def test_inclusion_pattern_restricts_to_matching_urls_only():
    settings = _settings(inclusion_patterns=["/clinical/"])
    assert should_fetch("https://sonohl.com/clinical/studies", "sonohl.com", settings) is True
    assert should_fetch("https://sonohl.com/careers", "sonohl.com", settings) is False
