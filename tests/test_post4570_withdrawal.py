"""The exact-post job must fail closed and never repeat a write."""

import copy
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

spec = importlib.util.spec_from_file_location(
    "withdraw_post4570", Path(__file__).parents[1] / "scripts" / "withdraw_post4570.py"
)
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)

RENDERED = (
    "<p>When users encounter this message, it often means the owner of the content has limited its visibility. This could be due to sharing settings that restrict access to a small group or specific individuals.</p>\n"
    "<p>Alternatively, the content may have been deleted by the owner, making it no longer available to the public or designated viewers.</p>\n"
    "<p>This message serves as a reminder that access to certain online content depends on the owner\u2019s privacy preferences and actions.</p>\n"
    '<p><em>Source: <a href="https://www.facebook.com/368218062001208/posts/1508469661309370" target="_blank" rel="noopener">Original Article</a></em></p>\n'
)


def response(data=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


@pytest.fixture
def route():
    before = {
        "id": 4570,
        "link": job.LINK,
        "status": "publish",
        "slug": job.SLUG,
        "title": {"raw": job.TITLE, "rendered": job.TITLE},
        "content": {"raw": RENDERED, "rendered": RENDERED},
        "featured_media": 4569,
        "excerpt": {"raw": "Summary"},
        "date": "2026-10-04T03:07:37",
        "date_gmt": "2026-10-04T03:07:37",
        "categories": [2],
        "tags": [],
        "author": 1,
    }
    after = copy.deepcopy(before)
    after["status"] = "draft"
    session = Mock()
    session.get.side_effect = [response(before), response(after)]
    session.post.return_value = response()
    public = Mock(side_effect=[response({"code": "rest_cannot_read"}, 401), response(status=404)])
    return before, after, session, public


def test_exact_status_only_write_and_public_readback(route):
    before, after, session, public = route
    assert job._digest(RENDERED) == job.BODY_SHA256
    report = job.withdraw(job.BASE, session, public)
    assert report["verified"] and report["status_only"]
    assert report["after_status"] == "draft" and report["featured_media"] == 4569
    session.post.assert_called_once_with(
        job.BASE + "/wp-json/wp/v2/posts/4570",
        json={"status": "draft"},
        timeout=(10, 30),
        allow_redirects=False,
    )
    assert public.call_count == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 4568),
        ("status", "draft"),
        ("link", "https://example.com/post"),
        ("slug", "real-news"),
        ("title", {"raw": "Real news"}),
        ("featured_media", 1),
        ("content", {"rendered": RENDERED + "<p>Edited.</p>", "raw": RENDERED}),
    ],
)
def test_any_identity_or_content_mismatch_prevents_write(route, field, value):
    before, _, session, public = route
    before[field] = value
    with pytest.raises(ValueError):
        job.withdraw(job.BASE, session, public)
    session.post.assert_not_called()
    public.assert_not_called()


def test_wrong_site_prevents_all_requests(route):
    _, _, session, public = route
    with pytest.raises(ValueError):
        job.withdraw("https://example.com", session, public)
    assert session.mock_calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "publish"),
        ("content", {"raw": "Changed"}),
        ("featured_media", 0),
        ("title", {"raw": "Changed"}),
        ("categories", [4]),
        ("tags", [3]),
    ],
)
def test_readback_change_fails_without_retrying_write(route, field, value):
    _, after, session, public = route
    after[field] = value
    with pytest.raises(ValueError):
        job.withdraw(job.BASE, session, public)
    session.post.assert_called_once()
    public.assert_not_called()


def test_uncertain_write_never_retries(route):
    _, _, session, public = route
    session.post.side_effect = requests.Timeout()
    with pytest.raises(requests.Timeout):
        job.withdraw(job.BASE, session, public)
    session.post.assert_called_once()
    assert session.get.call_count == 1
    public.assert_not_called()


@pytest.mark.parametrize("status,code", [(200, None), (403, "waf_block"), (500, "error")])
def test_public_access_or_unrelated_error_cannot_count_as_withdrawn(route, status, code):
    _, _, session, public = route
    public.side_effect = [response({"code": code}, status)]
    with pytest.raises(ValueError):
        job.withdraw(job.BASE, session, public)
    session.post.assert_called_once()


def test_cached_live_permalink_is_reported_as_unverified(route):
    _, _, session, public = route
    public.side_effect = [response({"code": "rest_cannot_read"}, 401), response(status=200)]
    with pytest.raises(ValueError):
        job.withdraw(job.BASE, session, public)
    session.post.assert_called_once()
