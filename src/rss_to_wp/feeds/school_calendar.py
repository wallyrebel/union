"""Upcoming break notices from the Union County School District in Mississippi."""

from datetime import datetime, timedelta
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from feedparser import FeedParserDict
import requests

DISTRICT = "https://www.union.k12.ms.us/"
ZONE = ZoneInfo("America/Chicago")
EVENT = re.compile(r"loadEventModal\('([a-fA-F0-9-]{36})','(\d{1,2}/\d{1,2}/\d{4}) [^']+','[^']+'\)")


def break_notices(html, now):
    page = BeautifulSoup(html, "html.parser")
    files = {a["href"] for a in page.select("a[href]") if re.fullmatch(
        r"(?:\d{4}-\d{4} )?District Calendar", a.get_text(" ", strip=True), re.I
    ) and re.fullmatch(r"https://content\.myconnectsuite\.com/api/documents/[a-zA-Z0-9]+", a["href"])}
    if len(files) != 1 or "New Albany, MS" not in page.get_text(" ", strip=True):
        raise ValueError("Mississippi district calendar identity unavailable")
    calendar = files.pop()
    events = {}
    for a in page.select("a.cs-link[onclick]"):
        event = EVENT.fullmatch(a["onclick"].strip())
        if event:
            event_date = datetime.strptime(event[2], "%m/%d/%Y").replace(tzinfo=ZONE)
            label = " ".join(a.stripped_strings).casefold()
            events.setdefault(label, set()).add((event_date, event[1]))
    entries = []
    for label, starts in events.items():
        kind = re.fullmatch(r"(thanksgiving|christmas|winter|spring|fall) break begins", label)
        if not kind or len(starts) != 1:
            continue
        returns = events.get(f"return from {kind[1]} break", set())
        if len(returns) != 1:
            continue
        start, event_id = next(iter(starts))
        end, _ = next(iter(returns))
        # This is an advance calendar item. The eligibility date is for scheduling,
        # and is never described as an announcement or as the day of the event.
        eligible = start - timedelta(days=3)
        if not eligible <= now < start or not 1 <= (end-start).days <= 30:
            continue
        holiday = kind[1].title() + " Break"
        start_text = start.strftime("%A, %B %d, %Y").replace(" 0", " ")
        return_text = end.strftime("%A, %B %d, %Y").replace(" 0", " ")
        source = calendar + "#:~:text=" + quote(holiday.split()[0])
        evidence = (f"The Union County School District in Mississippi lists {start_text} as the beginning of {holiday}. "
                    f"The district lists {return_text} as the return date on its public events calendar. "
                    "The school district also links its academic calendar for families.")
        schools = sorted({a.get_text(" ", strip=True) for a in page.select("a[href]")
                          if re.fullmatch(r"https://[a-z]+\.union\.k12\.ms\.us/?", a["href"])
                          and a.get_text(" ", strip=True).endswith(" Attendance Center")})
        if schools:
            evidence += " The district lists these schools: " + ", ".join(schools) + "."
        entries.append(FeedParserDict(id="union-k12:"+event_id, link=source,
                       title=f"Union County schools list {kind[1].title()} break and return dates",
                       summary=evidence, published=eligible.isoformat()))
    return FeedParserDict(entries=entries, feed={"title":"Union County School District, Mississippi"})


def district_calendar():
    response = requests.get(DISTRICT, timeout=(5, 15), allow_redirects=False,
                            headers={"User-Agent":"UnionCountyNews/1.0 (+https://unionnewsms.com/)", "Accept-Encoding":"gzip, deflate"})
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError("District calendar unavailable")
    return break_notices(response.content, datetime.now(ZONE))
