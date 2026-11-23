"""An issued point forecast for wet Thanksgiving travel, once per city and year."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from feedparser import FeedParserDict
import requests

CENTRAL = ZoneInfo("America/Chicago")


def travel_forecast(grid, city, public_map, now=None):
    now = now or datetime.now(CENTRAL)
    first = date(now.year, 11, 1)
    holiday = first + timedelta(days=(3 - first.weekday()) % 7 + 21)
    feed = FeedParserDict(entries=[], feed={"title":"National Weather Service Memphis"})
    if not holiday - timedelta(days=3) <= now.date() < holiday - timedelta(days=1):
        return feed
    r = requests.get(grid, timeout=(5, 18), allow_redirects=False, headers={
        "User-Agent":"MississippiNewsGroup/1.0 (+https://msnewsgroup.com/)", "Accept":"application/geo+json"})
    r.raise_for_status()
    if r.status_code != 200:
        raise ValueError("NWS point forecast unavailable")
    properties = r.json()["properties"]
    issued = datetime.fromisoformat(properties["updateTime"].replace("Z", "+00:00")).astimezone(CENTRAL)
    if not timedelta(0) <= now-issued <= timedelta(hours=24):
        return feed
    relevant = []
    wet = False
    for period in properties["periods"]:
        start = datetime.fromisoformat(period["startTime"]).astimezone(CENTRAL)
        if not holiday - timedelta(days=2) <= start.date() <= holiday:
            continue
        probability = (period.get("probabilityOfPrecipitation") or {}).get("value") or 0
        if start.date() == holiday - timedelta(days=1) and period["isDaytime"]:
            wet = probability >= 70 and "rain" in period["detailedForecast"].lower()
        relevant.append((start.date(), f"{period['name']} ({start:%B %d}): {period['detailedForecast']}"))
    if wet and any(day == holiday for day, _ in relevant):
        notes = [f"The National Weather Service Memphis point forecast for {city}, Mississippi, was updated {issued:%B %d, %Y at %I:%M %p} Central. These are forecast probabilities and possible rainfall amounts for this location.",
                 *(text for _,text in relevant)]
        feed.entries.append(FeedParserDict(id=f"nws-thanksgiving:{city}:{holiday}", link=public_map,
                 title=f"National Weather Service forecasts rain in {city} Wednesday before Thanksgiving",
                 published=issued.isoformat(), summary=" ".join(notes)))
    return feed
