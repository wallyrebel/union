"""Public holiday closures listed by the Union County Heritage Museum."""

from datetime import datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from feedparser import FeedParserDict

CALENDAR = "https://ucheritagemuseum.com/calendar/"
ZONE = ZoneInfo("America/Chicago")


def closure_notices(html, now):
    page = BeautifulSoup(html, "html.parser")
    contact = next((w for w in page.select(".textwidget")
                    if "UC Heritage Museum" in w.get_text(" ", strip=True)
                    and "New Albany, Mississippi" in w.get_text(" ", strip=True)), None)
    if contact is None or not page.select_one(".simcal-calendar"):
        raise ValueError("Museum calendar or New Albany location unavailable")
    details = " ".join(contact.stripped_strings)
    entries = {}
    for event in page.select("li.simcal-event"):
        label = event.select_one('.simcal-event-title[itemprop="name"]')
        first = event.select_one('[itemprop="startDate"][content]')
        last = event.select_one('[itemprop="endDate"][content]')
        if not label or not first or not last:
            continue
        title = label.get_text(" ", strip=True)
        if not title.casefold().startswith("museum closed"):
            continue
        start = datetime.fromisoformat(first["content"]).astimezone(ZONE).date()
        end = datetime.fromisoformat(last["content"]).astimezone(ZONE).date()
        eligible = datetime.combine(start-timedelta(days=5), time.min, ZONE)
        if now < eligible or now.date() >= start or not start <= end <= start+timedelta(days=14):
            continue
        key = f"uchm-closure-{start}-{end}"
        source = CALENDAR + "#:~:text=" + quote(title, safe="") + "&text=" + quote(first.get_text(strip=True), safe="")
        summary = (f"The Union County Heritage Museum in New Albany lists this event on its calendar: {title}. "
                   f"First day of the closure: {start:%A, %B %d, %Y}. "
                   f"Last day of the closure, inclusive: {end:%A, %B %d, %Y}. "
                   f"The museum lists these regular hours and visitor contact details: {details}")
        entries[key] = FeedParserDict(id=key, title=f"{title} in New Albany, {start:%B %d}–{end:%B %d}",
                                      link=source, summary=summary, published=eligible.isoformat())
    return FeedParserDict(entries=list(entries.values()), feed={"title":"Union County Heritage Museum"})
