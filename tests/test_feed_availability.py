from unittest.mock import Mock

import pytest
import requests

from rss_to_wp import cli
from rss_to_wp.config import FeedConfig
from rss_to_wp.feeds import parser


@pytest.mark.parametrize("body,errors", [
    (b'<rss version="2.0"><channel><title>News</title></channel></rss>', 0),
    (b'<html><body>Service unavailable</body></html>', 1),
    (None, 1),
])
def test_empty_source_and_failed_fetch_have_different_results(monkeypatch, body, errors):
    response = Mock(content=body, url="https://example.org/news", headers={})
    fetch = Mock(return_value=response, side_effect=requests.Timeout if body is None else None)
    monkeypatch.setattr(parser.requests, "get", fetch)
    result = cli.process_feed(FeedConfig(name="News", url=response.url), Mock(), Mock(), Mock(), Mock(),
                              False, 48, Mock())
    assert result == (0, 0, errors)
    assert fetch.call_args.kwargs["timeout"] == (10, 30)


def test_editorially_accepted_story_with_no_optional_image(monkeypatch):
    editor, wp = Mock(), Mock()
    title = "Library moves Thursday meeting to the auditorium"
    body = "The public library moved Thursday's board meeting to the auditorium while repairs continue in its usual meeting room."
    editor.rewrite.return_value = {"headline": title, "body": "<p>" + body + "</p>"}
    wp.create_post.return_value = {"id": 10, "link": "https://example.org/story"}
    monkeypatch.setattr(cli, "find_rss_image", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "find_fallback_image", lambda **kwargs: None)
    result = cli.process_entry({"title": title, "summary": body, "link": "https://library.example/meeting"},
                               FeedConfig(name="Library", url="https://library.example/feed"),
                               Mock(), editor, wp, False, Mock())
    assert result == wp.create_post.return_value
    wp.upload_media.assert_not_called()
    assert wp.create_post.call_args.kwargs["featured_media_id"] is None
