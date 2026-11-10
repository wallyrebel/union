"""A story the model keeps declining is held instead of re-sent every run."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pendulum
import pytest

from rss_to_wp import cli
from rss_to_wp.config import FeedConfig
from rss_to_wp.rewriter import OpenAIRewriter
from rss_to_wp.storage import DedupeStore

CONTENT = "Here is what is happening this week in athletics. " * 3


def completion(value):
    return SimpleNamespace(
        usage=None,
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(value)))],
    )


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    entry = {
        "id": "weekly-teaser",
        "link": "https://example.com/source",
        "title": "Here is what is happening this week in athletics",
        "published": pendulum.now("UTC").to_iso8601_string(),
        "summary": CONTENT,
    }
    monkeypatch.setattr(cli, "parse_feed", lambda _: SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    editor = OpenAIRewriter(api_key="offline-test", model="gpt-6-luna")
    editor.client = Mock()
    monkeypatch.setattr(editor, "_rate_limit", lambda: None)
    store = DedupeStore(tmp_path / "processed.db")
    feed = FeedConfig(name="News", url="https://example.com/feed")
    settings = SimpleNamespace(timezone="UTC")

    def run(dry_run=False):
        return cli.process_feed(feed, settings, store, editor, Mock(), dry_run, 48, Mock())

    return SimpleNamespace(run=run, store=store, create=editor.client.chat.completions.create)


def test_declined_story_is_held_after_three_runs(pipeline):
    pipeline.create.return_value = completion({"headline": None, "excerpt": "", "body": None})
    for _ in range(cli.MAX_REWRITE_ATTEMPTS):
        assert pipeline.run() == (0, 0, 1)
    calls = pipeline.create.call_count
    assert calls >= cli.MAX_REWRITE_ATTEMPTS
    # Later runs skip the story without another model request.
    assert pipeline.run() == (0, 1, 0)
    assert pipeline.run() == (0, 1, 0)
    assert pipeline.create.call_count == calls
    attempts, reason = pipeline.store.rejection_state("id:weekly-teaser")
    assert attempts == cli.MAX_REWRITE_ATTEMPTS and reason == "invalid_output_fields"
    assert not pipeline.store.is_processed("id:weekly-teaser")
    assert pipeline.store.get_processed_count() == 0


def test_api_errors_and_dry_runs_never_count(pipeline):
    pipeline.create.side_effect = RuntimeError("offline API failure")
    for _ in range(cli.MAX_REWRITE_ATTEMPTS + 2):
        assert pipeline.run() == (0, 0, 1)
    assert pipeline.store.rejection_state("id:weekly-teaser") == (0, None)

    pipeline.create.side_effect = None
    pipeline.create.return_value = completion({"headline": None, "excerpt": "", "body": None})
    for _ in range(cli.MAX_REWRITE_ATTEMPTS + 2):
        pipeline.run(dry_run=True)
    assert pipeline.store.rejection_state("id:weekly-teaser") == (0, None)
