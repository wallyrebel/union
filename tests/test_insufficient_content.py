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


# Exact source that published post 4570 on October 4 despite the 50-char guard.
FACEBOOK_TITLE = "This content isn't available right now"
FACEBOOK_NOTICE = (
    "When this happens, it's usually because the owner only shared it with a small "
    "group of people, changed who can see it or it's been deleted."
)


@pytest.mark.parametrize(
    "title,content",
    [
        (FACEBOOK_TITLE, FACEBOOK_NOTICE),
        ("A post from New Albany Fire/Rescue", FACEBOOK_NOTICE),
        ("THIS CONTENT ISN’T AVAILABLE RIGHT NOW", "<p>" + FACEBOOK_NOTICE + "</p>"),
        ("Source headline", "<h1>" + FACEBOOK_TITLE + "</h1><p>" + FACEBOOK_NOTICE + "</p>"),
        ("Log in to Facebook", "Log in to Facebook to view this post and continue browsing."),
        (
            "Facebook – log in or sign up",
            "Log in to Facebook to view this post and continue browsing.",
        ),
        ("Source headline", "<h1>Something went wrong</h1><p>Please try again later.</p>"),
        (
            "Source headline",
            "<h1>Sorry, this page isn't available</h1><p>The link you followed may be broken, or the page may have been removed.</p>",
        ),
        ("Access denied", "Access to this page was denied. Please contact the site administrator."),
        ("503 Service Unavailable", "<h1>Service unavailable</h1><p>Please try again later.</p>"),
    ],
)
def test_platform_source_is_retryable_skip_before_all_external_work(pipeline, title, content):
    assert pipeline.run(content, title=title) == (0, 1, 0)
    assert pipeline.run(content, title=title) == (0, 1, 0)
    pipeline.editor.rewrite.assert_not_called()
    cli.find_rss_image.assert_not_called()
    assert pipeline.wp.mock_calls == []
    assert pipeline.store.get_processed_count() == 0
    assert pipeline.logger.info.call_args[0] == ("entry_skipped_platform_placeholder",)


def test_confirmed_placeholder_can_gain_real_news_then_publish_once(pipeline):
    assert len(FACEBOOK_NOTICE) == 139
    assert pipeline.run(FACEBOOK_NOTICE, title=FACEBOOK_TITLE) == (0, 1, 0)
    assert pipeline.run(
        "City Hall will close Monday for the federal holiday.", title="City Hall closure"
    ) == (1, 0, 0)
    assert pipeline.run(
        "City Hall will close Monday for the federal holiday.", title="City Hall closure"
    ) == (0, 1, 0)


@pytest.mark.parametrize(
    "title,content",
    [
        (
            "Facebook privacy changes discussed at school board meeting",
            "School officials explained Facebook privacy settings and deletion rules during Tuesday's meeting.",
        ),
        (
            "Residents report Facebook outage",
            "Residents saw 'This content isn't available right now' during an outage Friday. The city kept alerts on its website.",
        ),
        (
            "County updates online portal",
            "Residents must log in to view tax records on the county's new website, officials said Monday.",
        ),
        (
            "City restores public records",
            "'This content isn't available right now' appeared on the city's page. Officials restored the records Friday.",
        ),
        ("City Hall closure", "City Hall will close Monday for the federal holiday."),
    ],
)
def test_real_short_news_and_reporting_on_platform_errors_still_publish(pipeline, title, content):
    assert pipeline.run(content, title=title) == (1, 0, 0)
    pipeline.editor.rewrite.assert_called_once()
    pipeline.wp.create_post.assert_called_once()


@pytest.mark.parametrize(
    "rewritten",
    [
        {"headline": "Headline", "body": ""},
        {"headline": "Headline", "body": "<p>&nbsp;</p><img src='photo.jpg'>"},
        {"headline": "<br>", "body": "<p>A real short story.</p>"},
        {"headline": "Headline", "body": None},
        {"body": "<p>A real short story.</p>"},
        ["headline", "body"],
        {"headline": FACEBOOK_TITLE, "body": FACEBOOK_NOTICE},
        {
            "headline": "Content Unavailable Due to Privacy Settings or Deletion",
            "body": "<p>The Facebook content cannot be viewed because the owner changed its privacy settings or deleted the post.</p>",
        },
        {"headline": "Source update", "body": "<p>" + FACEBOOK_NOTICE + "</p>"},
    ],
)
def test_invalid_rewrite_is_error_before_images_wp_or_dedupe(pipeline, rewritten):
    pipeline.editor.rewrite.return_value = rewritten
    assert pipeline.run(
        "County officials reopened Main Street after completing bridge repairs today."
    ) == (0, 0, 1)
    cli.find_rss_image.assert_not_called()
    assert pipeline.wp.mock_calls == []
    assert pipeline.store.get_processed_count() == 0


def test_direct_entry_caller_cannot_rewrite_platform_source(pipeline):
    entry = {"title": FACEBOOK_TITLE, "summary": FACEBOOK_NOTICE}
    assert (
        cli.process_entry(
            entry,
            pipeline.feed,
            SimpleNamespace(),
            pipeline.editor,
            pipeline.wp,
            False,
            pipeline.logger,
        )
        is None
    )
    pipeline.editor.rewrite.assert_not_called()
    assert pipeline.wp.mock_calls == []


def test_dry_run_also_rejects_invalid_output(pipeline):
    pipeline.editor.rewrite.return_value = {"headline": "Headline", "body": "<p>&nbsp;</p>"}
    entry = {
        "title": "News",
        "summary": "County officials reopened Main Street after completing bridge repairs today.",
    }
    assert (
        cli.process_entry(
            entry, pipeline.feed, SimpleNamespace(), pipeline.editor, None, True, pipeline.logger
        )
        is None
    )
    cli.find_rss_image.assert_not_called()
