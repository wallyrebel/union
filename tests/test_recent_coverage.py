import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rss_to_wp import cli
from rss_to_wp.recent_coverage import candidates
from rss_to_wp.rewriter import OpenAIRewriter
from rss_to_wp.wordpress import WordPressClient


def post(post_id, headline, body):
    return {"id": post_id, "status": "publish", "date_gmt": "2026-11-26T22:32:12",
            "title": {"rendered": headline}, "content": {"rendered": "<p>" + body + "</p>"}}


MARKER = post(5417, "Marker dedication planned at Tallahatchie River Bridge",
              "The final journey of Meriwether Lewis will be commemorated Dec. 2 at 10 a.m. "
              "on the Tallahatchie River Bridge in New Albany, the Union County Heritage Museum said.")
SHOPPING = post(5419, "New Albany businesses plan Thanksgiving night shopping event",
                "Turkey to Tinsel runs from 8 to 11 p.m. Thanksgiving night in downtown New Albany. "
                "More than 26 businesses will participate. Some stores may open earlier.")
EXAMPLES = [
    ("Historic marker honoring Meriwether Lewis to be unveiled in New Albany",
     "Join us Dec. 2 at 10 a.m. on the Tallahatchie River Bridge for the historic marker "
     "dedication commemorating the final journey of Meriwether Lewis.", 5417),
    ("New Albany shops promote Thanksgiving night shopping event",
     "Turkey to Tinsel returns to downtown New Albany on Thanksgiving night. "
     "Stores are scheduled to open from 8 to 11 p.m. Some may open earlier.", 5419),
    ("Museum moves Meriwether Lewis marker ceremony indoors",
     "The Union County Heritage Museum has moved the Dec. 2 Meriwether Lewis marker ceremony "
     "from the Tallahatchie River Bridge into the museum because of flooding.", 0),
]


def test_shortlist_finds_the_actual_reposts_and_excludes_private_text():
    private = dict(MARKER, id=123, status="private")
    for title, source, expected in EXAMPLES:
        matches = candidates(title, source, [MARKER, SHOPPING, private])
        assert {p["id"] for p in matches} == {expected or 5417}
    assert candidates("City budgets", "Aldermen approved a street resurfacing contract.", [MARKER]) == []


def test_public_pagination_and_cache(monkeypatch):
    wp = WordPressClient("https://example.com", "test", "test")
    monkeypatch.setattr(wp, "_rate_limit", lambda: None)
    wp.session = Mock()
    pages = [Mock(headers={"X-WP-TotalPages": "2"}) for _ in range(2)]
    for response, record in zip(pages, [MARKER, SHOPPING]):
        response.json.return_value = [record]
    wp.session.get.side_effect = pages
    assert wp.recent_public_posts() == wp.recent_public_posts() == [MARKER, SHOPPING]
    assert [call.kwargs["params"]["page"] for call in wp.session.get.call_args_list] == [1, 2]
    assert all(call.kwargs["params"]["status"] == "publish" for call in wp.session.get.call_args_list)


@pytest.mark.parametrize("answer", [None, True, 9999, "5417"])
def test_uncertain_or_invalid_match_never_clears_for_publication(monkeypatch, answer):
    editor = OpenAIRewriter(api_key="test", model="gpt-6-luna", fallback_model="gpt-6-luna")
    monkeypatch.setattr(editor, "_rate_limit", lambda: None)
    choice = SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
        content=json.dumps({"matched_id": answer})))
    monkeypatch.setattr(editor.client.chat.completions, "create", Mock(return_value=SimpleNamespace(choices=[choice])))
    with pytest.raises(RuntimeError):
        editor.covered_event("Marker", "Marker dedication", "2026-11-25", [MARKER])


def test_repeat_from_another_url_stops_before_media(monkeypatch):
    title, source, _ = EXAMPLES[0]
    editor, wp, logger = Mock(), Mock(), Mock()
    editor.rewrite.return_value = {"headline": title, "body": "<p>"+source+"</p>"}
    wp.check_duplicate_by_source_url.return_value = False
    wp.recent_public_posts.return_value = [MARKER]
    editor.covered_event.return_value = 5417
    image = Mock()
    monkeypatch.setattr(cli, "find_rss_image", image)
    result = cli.process_entry({"title": title, "summary": source,
                                "link": "https://www.facebook.com/example/posts/2"},
                               cli.FeedConfig(name="museum", url="https://example.com/feed"),
                               Mock(), editor, wp, False, logger)
    assert result == {"skip": True}
    image.assert_not_called()
    wp.create_post.assert_not_called()


@pytest.mark.skipif(os.getenv("CHECK_LIVE_EVENT_REVIEW") != "1", reason="manual read-only model check")
@pytest.mark.parametrize("title,source,expected", EXAMPLES)
def test_live_event_review(title, source, expected):
    model = os.environ.get("OPENAI_MODEL") or "gpt-6-luna"
    editor = OpenAIRewriter(api_key=os.environ["OPENAI_API_KEY"], model=model)
    related = candidates(title, source, [MARKER, SHOPPING])
    assert editor.covered_event(title, source, "2026-11-26", related) == expected
