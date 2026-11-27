"""Find public stories worth comparing before publishing another social post."""

from __future__ import annotations

import re

from rss_to_wp.source_content import clean_source_content


_COMMON = set(
    "that this from with will have been were their they about after said says "
    "there here more than also only into county mississippi albany local news "
    "source original article facebook posted page photos school high event "
    "please join share today tomorrow tonight downtown".split()
)


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]{4,}", text.casefold())) - _COMMON


def candidates(title: str, body: str, recent: list[dict]) -> list[dict]:
    incoming = _terms(clean_source_content(title + " " + body))
    matches = []
    for post in recent:
        if post["status"] != "publish" or post["content"].get("protected"):
            continue
        heading = clean_source_content(post["title"]["rendered"])
        article = clean_source_content(post["content"]["rendered"])
        overlap = incoming & _terms(heading + " " + article)
        if len(overlap) >= 4:
            matches.append((len(overlap), {
                "id": post["id"], "date_gmt": post["date_gmt"],
                "headline": heading, "body": article[:4500],
            }))
    return [post for _, post in sorted(matches, key=lambda match: match[0], reverse=True)]
