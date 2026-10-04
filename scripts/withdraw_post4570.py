"""Authorized status-only withdrawal, locked to the verified Union placeholder."""

import hashlib
import json
import os
from pathlib import Path

import requests

POST_ID = 4570
BASE = "https://unionnewsms.com"
LINK = BASE + "/mississippi-news/content-unavailable-due-to-privacy-settings-or-deletion-42/"
TITLE = "Content Unavailable Due to Privacy Settings or Deletion"
SLUG = "content-unavailable-due-to-privacy-settings-or-deletion-42"
BODY_SHA256 = "90ee5e71ec4a7afd9e9188dd591820138923961edaed56e1d0cb90943ad5c912"


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _read(session, endpoint):
    response = session.get(
        endpoint, params={"context": "edit"}, timeout=(10, 30), allow_redirects=False
    )
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError("Unexpected authenticated read status")
    return response.json()


def withdraw(base, session, public_get=requests.get):
    if base.rstrip("/") != BASE:
        raise ValueError("Unexpected WordPress host")
    endpoint = BASE + f"/wp-json/wp/v2/posts/{POST_ID}"
    before = _read(session, endpoint)
    if (
        before["id"] != POST_ID
        or before["link"] != LINK
        or before["status"] != "publish"
        or before["slug"] != SLUG
        or before["title"]["raw"] != TITLE
        or before["featured_media"] != 4569
        or _digest(before["content"]["rendered"]) != BODY_SHA256
    ):
        raise ValueError("Exact published post preconditions failed")

    # Exactly one write. Never retry an uncertain outcome or change body/media.
    result = session.post(
        endpoint, json={"status": "draft"}, timeout=(10, 30), allow_redirects=False
    )
    result.raise_for_status()
    if result.status_code != 200:
        raise ValueError("Unexpected write status")
    after = _read(session, endpoint)
    if after["id"] != POST_ID or after["status"] != "draft":
        raise ValueError("Draft status verification failed")
    for field in (
        "title",
        "content",
        "excerpt",
        "date",
        "date_gmt",
        "slug",
        "categories",
        "tags",
        "featured_media",
        "author",
    ):
        if after.get(field) != before.get(field):
            raise ValueError("Other post fields changed")

    public = public_get(endpoint, timeout=(10, 30), allow_redirects=False)
    if public.status_code not in (401, 403, 404) or public.json().get("code") not in (
        "rest_post_invalid_id",
        "rest_cannot_read",
    ):
        raise ValueError("Post remains accessible through public REST")
    page = public_get(LINK, timeout=(10, 30), allow_redirects=False)
    if page.status_code not in (404, 410):
        raise ValueError("Public permalink remains accessible")
    return {
        "post_id": POST_ID,
        "url": LINK,
        "before_status": "publish",
        "after_status": "draft",
        "status_only": True,
        "content_sha256": _digest(after["content"]["raw"]),
        "featured_media": after["featured_media"],
        "public_rest_status": public.status_code,
        "public_permalink_status": page.status_code,
        "verified": True,
    }


def main():
    report_path = Path("data/post4570-withdrawal.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.Session() as session:
            session.auth = (
                os.environ["WORDPRESS_USERNAME"],
                os.environ["WORDPRESS_APP_PASSWORD"],
            )
            report = withdraw(os.environ["WORDPRESS_BASE_URL"], session)
    except Exception as exc:
        # Error type only: never print request details, response bodies or auth.
        report = {"post_id": POST_ID, "verified": False, "error_type": type(exc).__name__}
    report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
