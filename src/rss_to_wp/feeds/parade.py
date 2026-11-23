"""Advance participant instructions from the organizer's dated parade page."""
from datetime import datetime, timedelta
import re

from bs4 import BeautifulSoup
from feedparser import FeedParserDict

from rss_to_wp.feeds.museum import ZONE

PARADE = "https://www.newalbanymainstreet.com/2026parade"


def participant_instructions(markup, now):
    page = BeautifulSoup(markup, "html.parser")
    canonical = page.select_one("link[rel=canonical]")
    if not canonical or canonical.get("href") != PARADE:
        raise ValueError("Unexpected parade page")
    paragraphs = [p.get_text(" ", strip=True) for p in page.select("main p")]
    label = next((p for p in paragraphs if p.startswith("When: ")), "")
    match = re.fullmatch(r"When: (\w+) (November \d{1,2}, 2026) at (\d{1,2}:\d\d[ap]m)", label, re.I)
    if not match:
        raise ValueError("Organizer's dated event time unavailable")
    day = datetime.strptime(match[2] + " " + match[3], "%B %d, %Y %I:%M%p").replace(tzinfo=ZONE)
    available = (day - timedelta(days=7)).replace(hour=0, minute=0)
    entries = []
    if day.strftime("%A") == match[1] and available <= now < day:
        details = [p for p in paragraphs if p.startswith(("The parade route passes beneath", "If your entry exceeds",
                   "Large Trucks & Oversized Vehicles ", "Other oversized or heavy vehicles",
                   "School Bands School bands", "Equestrian Entries Equestrian entries"))]
        if not all(any(marker in p for p in details) for marker in ("Tanglefoot Trail", "13 feet", "18-wheelers", "Band directors")):
            raise ValueError("Organizer's staging details incomplete")
        entries.append(FeedParserDict(id="new-albany-participant-instructions-" + str(day.date()),link=PARADE,
                       published=available.isoformat(),title="New Albany Christmas parade sets float height and staging rules",
                       summary=" ".join(["The New Albany Main Street Association lists the following instructions for registered participants in the New Albany and Union County Christmas Parade.", label, *details])))
    return FeedParserDict(entries=entries,feed={"title":"New Albany Main Street Association"})
