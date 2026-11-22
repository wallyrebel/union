"""RSS feed parsing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import feedparser
import requests
from feedparser.exceptions import CharacterEncodingOverride, NonXMLContentType

from rss_to_wp.feeds.golf import FEED as GOLF_FEED, local_golf
from rss_to_wp.utils import get_logger
from rss_to_wp.feeds.school_calendar import DISTRICT, district_calendar
from rss_to_wp.feeds.museum import CALENDAR, ZONE, closure_notices
from rss_to_wp.feeds.sanitation import STREETS, thanksgiving_routes

logger = get_logger("feeds.parser")


def parse_feed(url: str) -> Optional[dict[str, Any]]:
    """Parse an RSS/Atom feed from URL.

    Args:
        url: URL of the RSS feed.

    Returns:
        Parsed feed dictionary or None if parsing failed.
    """
    logger.info("parsing_feed", url=url)

    try:
        if url == DISTRICT:
            return district_calendar()
        local_calendars = {CALENDAR: closure_notices, STREETS: thanksgiving_routes}
        if url in local_calendars:
            response = requests.get(url, timeout=(5, 15), allow_redirects=False,
                                    headers={"Accept-Encoding": "gzip, deflate", "User-Agent": feedparser.USER_AGENT})
            if response.status_code != 200:
                raise ValueError("Local calendar unavailable")
            return local_calendars[url](response.content, datetime.now(ZONE))
        response = requests.get(url, timeout=(10, 30), headers={"User-Agent": feedparser.USER_AGENT})
        response.raise_for_status()
        headers = {key.lower(): value for key, value in response.headers.items()}
        headers.setdefault("content-location", response.url)
        headers.setdefault("content-type", "application/xml")
        feed = feedparser.parse(response.content, response_headers=headers)
        header_warning = isinstance(feed.get("bozo_exception"), (CharacterEncodingOverride, NonXMLContentType))
        if not feed.version or (feed.bozo and not feed.entries and not header_warning):
            logger.error("feed_invalid", url=url)
            return None

        # Check for parsing errors
        if feed.bozo and feed.bozo_exception:
            logger.warning(
                "feed_parse_warning",
                url=url,
                error=str(feed.bozo_exception),
            )
            # Continue anyway - feedparser often recovers

        if url == GOLF_FEED:
            return local_golf(feed, {"New Albany Bulldogs": "New Albany"})

        if not feed.entries:
            logger.info("feed_empty", url=url)
            return feed

        logger.info(
            "feed_parsed",
            url=url,
            entry_count=len(feed.entries),
            feed_title=feed.feed.get("title", "Unknown"),
        )

        return feed

    except Exception as e:
        logger.error("feed_parse_error", url=url, error=str(e))
        return None


def get_entry_content(entry: dict[str, Any]) -> str:
    """Extract the best available content from an RSS entry.

    Prefers full content over summary.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Content string (may be HTML).
    """
    # Try content first (usually full article)
    if "content" in entry and entry["content"]:
        # content is usually a list
        contents = entry["content"]
        if isinstance(contents, list) and len(contents) > 0:
            return contents[0].get("value", "")

    # Fall back to summary
    if "summary" in entry:
        return entry.get("summary", "")

    # Last resort: description
    return entry.get("description", "")


def get_entry_link(entry: dict[str, Any]) -> Optional[str]:
    """Get the link URL from an RSS entry.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Link URL or None.
    """
    # Direct link attribute
    if "link" in entry and entry["link"]:
        return entry["link"]

    # Links list
    if "links" in entry and entry["links"]:
        for link in entry["links"]:
            if link.get("rel") == "alternate" or link.get("type") == "text/html":
                return link.get("href")
        # Return first link as fallback
        return entry["links"][0].get("href")

    return None


def get_entry_title(entry: dict[str, Any]) -> str:
    """Get the title from an RSS entry.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Title string.
    """
    return entry.get("title", "Untitled")
