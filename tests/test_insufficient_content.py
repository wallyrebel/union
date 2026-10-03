"""Insufficient input is a retryable local skip, never a publication failure."""

from types import SimpleNamespace
from unittest.mock import Mock

import pendulum
import pytest

from rss_to_wp import cli
from rss_to_wp.config import FeedConfig
from rss_to_wp.feeds import generate_entry_key
from rss_to_wp.rewriter import OpenAIRewriter
from rss_to_wp.source_content import clean_source_content
from rss_to_wp.storage import DedupeStore


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    entries = []
    monkeypatch.setattr(cli, "parse_feed", lambda _: SimpleNamespace(entries=entries))
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(cli, "find_rss_image", Mock(return_value="https://example.com/photo.jpg"))
    monkeypatch.setattr(
        cli, "download_image", Mock(return_value=(b"image", "photo.jpg", "image/jpeg"))
    )
    store = DedupeStore(tmp_path / "processed.db")
    editor = Mock()
    editor.rewrite.return_value = {"headline": "Verified headline", "body": "<p>Source story.</p>"}
    wp = Mock()
    wp.create_post.return_value = {"id": 42, "link": "https://example.com/story"}
    logger = Mock()
    feed = FeedConfig(name="News", url="https://example.com/feed")
    settings = SimpleNamespace(timezone="UTC")

    def run(content, **updates):
        entries[:] = [
            {
                "id": "same-guid",
                "link": "https://example.com/source",
                "title": "Source headline with enough words to be a long title",
                "published": pendulum.now("UTC").to_iso8601_string(),
                "summary": content,
                **updates,
            }
        ]
        return cli.process_feed(feed, settings, store, editor, wp, False, 48, logger)

    return SimpleNamespace(
        run=run, store=store, editor=editor, wp=wp, logger=logger, entries=entries, feed=feed
    )


@pytest.mark.parametrize(
    "content",
    [
        "",
        " \n\t",
        "x",
        "x" * 49,
        '<img src="photo.jpg" alt="A long image label">',
        "<script>" + "x" * 100 + "</script><p>&nbsp;</p>",
    ],
)
def test_insufficient_input_is_skip_without_api_or_wp(pipeline, content):
    assert pipeline.run(content) == (0, 1, 0)
    assert pipeline.run(content) == (0, 1, 0)
    pipeline.editor.rewrite.assert_not_called()
    cli.find_rss_image.assert_not_called()
    pipeline.wp.create_post.assert_not_called()
    assert pipeline.store.get_processed_count() == 0
    assert pipeline.logger.info.call_args[0] == ("entry_skipped_insufficient_content",)
    assert pipeline.logger.info.call_args.kwargs["length"] < 50


def test_same_guid_and_url_can_gain_caption_then_publish_once(pipeline):
    assert pipeline.run('<img src="photo.jpg">') == (0, 1, 0)
    key = generate_entry_key(pipeline.entries[0], pipeline.feed.url)
    assert not pipeline.store.is_processed(key)
    caption = "County officials reopened Main Street after completing bridge repairs today."
    assert pipeline.run(caption) == (1, 0, 0)
    pipeline.editor.rewrite.assert_called_once_with(
        content=caption, original_title=pipeline.entries[0]["title"], use_original_title=False
    )
    assert pipeline.store.is_processed(key)
    assert pipeline.run(caption) == (0, 1, 0)
    pipeline.wp.create_post.assert_called_once()


def test_existing_50_character_boundary_is_preserved(pipeline):
    assert pipeline.run("x" * 50) == (1, 0, 0)
    pipeline.editor.rewrite.assert_called_once()


@pytest.mark.parametrize("failure", [None, RuntimeError("generation unavailable")])
def test_genuine_generation_failure_stays_error(pipeline, failure):
    if isinstance(failure, Exception):
        pipeline.editor.rewrite.side_effect = failure
    else:
        pipeline.editor.rewrite.return_value = failure
    assert pipeline.run("x" * 50) == (0, 0, 1)
    assert pipeline.store.get_processed_count() == 0
    pipeline.wp.create_post.assert_not_called()


@pytest.mark.parametrize("failure", [None, RuntimeError("WordPress unavailable")])
def test_wordpress_failure_stays_error(pipeline, failure):
    if isinstance(failure, Exception):
        pipeline.wp.create_post.side_effect = failure
    else:
        pipeline.wp.create_post.return_value = failure
    assert pipeline.run("x" * 50) == (0, 0, 1)
    assert pipeline.store.get_processed_count() == 0


def test_rewriter_and_preflight_share_normalization(monkeypatch):
    editor = OpenAIRewriter(api_key="test-only")
    monkeypatch.setattr(editor, "_rate_limit", lambda: None)
    api = Mock()
    monkeypatch.setattr(editor.client.chat.completions, "create", api)
    source = "<style>" + "x" * 100 + "</style><p>&nbsp;Short caption</p>"
    assert clean_source_content(source) == editor._strip_html(source) == "Short caption"
    assert editor.rewrite(source, "Long title " * 10) is None
    api.assert_not_called()
    api.side_effect = RuntimeError("API unavailable")
    assert editor.rewrite("x" * 50, "Title") is None
    expected_models = [editor.model]
    fallback = getattr(editor, "fallback_model", None)
    if fallback and fallback != editor.model:
        expected_models.append(fallback)
    assert [call.kwargs["model"] for call in api.call_args_list] == expected_models
