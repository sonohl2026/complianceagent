"""robots.txt handling, decoupled from fetching so it's unit-testable
without a live network call: pass in already-fetched (or absent) content."""

import urllib.robotparser as robotparser


def build_robots_parser(robots_txt_content: str | None, robots_url: str) -> robotparser.RobotFileParser:
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    # Standard convention: a missing/unfetchable robots.txt means allow-all.
    parser.parse((robots_txt_content or "").splitlines())
    return parser


def is_allowed(parser: robotparser.RobotFileParser, user_agent: str, url: str) -> bool:
    return parser.can_fetch(user_agent, url)


def crawl_delay(parser: robotparser.RobotFileParser, user_agent: str) -> float | None:
    return parser.crawl_delay(user_agent)
