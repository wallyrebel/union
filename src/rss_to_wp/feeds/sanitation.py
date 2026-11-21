"""Advance notice of the city's expressly dated Thanksgiving garbage routes."""

from datetime import date, datetime, time, timedelta
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from feedparser import FeedParserDict

from rss_to_wp.feeds.museum import ZONE

STREETS = "https://www.visitnewalbany.com/streets-sanitation"


def thanksgiving_routes(html, now):
    main = BeautifulSoup(html, "html.parser").select_one("main")
    text = " ".join(main.stripped_strings).replace("\u200b", "") if main else ""
    heading = re.search(
        r"CITY OF NEW ALBANY\s*[-–]\s*HOLIDAY LIST\s*/\s*GARBAGE SCHEDULE\s*[-–]+\s*(\d{4})",
        text,
        re.I,
    )
    if not heading:
        raise ValueError("New Albany garbage schedule unavailable")
    match = re.search(
        r"Thanksgiving Day\s*[-–]\s*Thursday\s*[-–]\s*Nov\.?\s*(\d{1,2}),?\s*Friday\s*[-–]\s*Nov\.?\s*(\d{1,2})\s*\(Thursday/Friday routes will be picked up on Wednesday before Thanksgiving\)",
        text[heading.end() :],
        re.I,
    )
    entries = []
    if match:
        holiday = date(int(heading[1]), 11, int(match[1]))
        friday = date(holiday.year, 11, int(match[2]))
        pickup = holiday - timedelta(days=1)
        available = datetime.combine(pickup - timedelta(days=4), time.min, ZONE)
        if (
            holiday.weekday() == 3
            and friday == holiday + timedelta(days=1)
            and available <= now
            and now.date() < pickup
        ):
            details = text[: heading.start()].strip()
            source = (
                STREETS
                + "#:~:text="
                + quote(heading[0], safe="")
                + "&text="
                + quote("Thanksgiving Day", safe="")
            )
            note = (
                f"The City of New Albany's {holiday.year} garbage schedule moves both Thursday and Friday garbage routes "
                f"to {pickup:%A, %B %d, %Y}. The schedule lists {holiday:%A, %B %d} and {friday:%A, %B %d} "
                "as Thanksgiving holidays. This Wednesday collection is specifically for both Thursday and Friday city garbage routes. "
                f"The same street department page gives this contact and service information: {details}"
            )
            entries.append(
                FeedParserDict(
                    id=f"new-albany-garbage-{holiday}",
                    link=source,
                    title=f"New Albany moves Thanksgiving garbage routes to Wednesday, {pickup:%B %d}",
                    summary=note,
                    published=available.isoformat(),
                )
            )
    return FeedParserDict(entries=entries, feed={"title": "City of New Albany Street Department"})
