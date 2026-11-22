"""Local team and golfer results from newly released MHSAA championship scorecards."""

import calendar
import re
from datetime import datetime, timedelta, timezone
from html import escape

import requests
from bs4 import BeautifulSoup
from feedparser import FeedParserDict

FEED = "https://www.misshsaa.com/feed/"
ASSOCIATION = "Mississippi High School Activities Association"


def scorecard(document, url, schools, release_date):
    page = BeautifulSoup(document, "html.parser")
    canonical = page.select_one('link[rel="canonical"]')
    body = page.select_one("article .entry")
    if not canonical or canonical.get("href") != url or not body:
        raise ValueError("MHSAA scorecard identity or body missing")
    event = body.find(string=re.compile(r"^\d{4} MHSAA Class \d+A (Boys|Girls) Golf Championship$"))
    teams = body.find("summary", string="All teams")
    players = body.find("h2", string="Individual Results")
    if not event or not teams or not players:
        return None
    details = list(event.parent.parent.stripped_strings)
    if len(details) != 6 or details[1] != event.strip():
        return None
    _, event_name, _, competition_date, course, city = details
    team_results = []
    local_names = []
    for row in teams.parent.select("div > div"):
        cells = list(row.stripped_strings)
        if len(cells) != 4 or not valid_scores(cells):
            continue
        rank, name, rounds, total = cells
        if name in schools:
            local_names.append(name)
        team_results.append(f"{name}, place {rank}, rounds {rounds}, total {total}")
    if not local_names:
        return None
    player_results = []
    for row in players.parent.find_all("div"):
        cells = list(row.stripped_strings)
        if len(cells) != 5 or not valid_scores(cells):
            continue
        rank, player, school, rounds, total = cells
        if school in schools.values() or rank == "1":
            player_results.append(f"{player}, {school}, place {rank}, rounds {rounds}, total {total}")
    if not player_results or not any(f", {schools[name]}, place " in row for name in local_names for row in player_results):
        return None
    headline = f"{' and '.join(local_names)} results at the {event_name}"
    notes = [
        f"MHSAA published the official results on {release_date:%B %d, %Y} for the {event_name}. "
        f"The scorecard lists the competition date as {competition_date} at {course} in {city}.",
        "The following team standings are in official order. T indicates a tie. " + ". ".join(team_results) + ".",
        "Individual results for local players and the champion follow. " + ". ".join(player_results) + ".",
    ]
    for note in teams.parent.parent.find_all("p", recursive=False):
        notes.append(note.get_text(" ", strip=True))
    return headline, "".join(f"<p>{escape(note)}</p>" for note in notes)


def valid_scores(cells):
    rounds = re.fullmatch(r"(\d+) \+ (\d+)", cells[-2])
    total = re.fullmatch(r"(\d+) \((?:E|[+-]\d+)\)", cells[-1])
    return (re.fullmatch(r"T?[1-9]\d*", cells[0]) and rounds and total
            and int(rounds[1]) + int(rounds[2]) == int(total[1]))


def local_golf(feed, schools):
    if feed.feed.get("title") != ASSOCIATION or feed.feed.get("link", "").rstrip("/") != FEED.removesuffix("feed/").rstrip("/"):
        raise ValueError("Unexpected association feed")
    now = datetime.now(timezone.utc)
    entries = []
    for item in feed.entries:
        if not any(tag.get("term") == "Golf Championships" for tag in item.get("tags", [])):
            continue
        url = item.get("link", "")
        published = item.get("published_parsed")
        if not published or not re.fullmatch(r"https://www\.misshsaa\.com/\d{4}/\d{2}/\d{2}/[a-z0-9-]+/", url):
            continue
        date = datetime.fromtimestamp(calendar.timegm(published), timezone.utc)
        if not now - timedelta(hours=48) <= date <= now:
            continue
        response = requests.get(url, timeout=(6, 18), allow_redirects=False,
                                headers={"User-Agent": "MississippiNewsGroup/1.0", "Accept-Encoding": "gzip, deflate"})
        response.raise_for_status()
        selected = scorecard(response.content, url, schools, date)
        if selected:
            title, summary = selected
            entries.append(FeedParserDict(id=url, link=url, title=title, summary=summary,
                                          published=item.published, published_parsed=published))
    return FeedParserDict(feed={"title": ASSOCIATION}, entries=entries)
