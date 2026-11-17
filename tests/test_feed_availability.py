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
