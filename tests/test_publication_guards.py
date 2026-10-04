"""Exercise rewriter parsing/fallback and direct WordPress boundary checks offline."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rss_to_wp.rewriter import OpenAIRewriter
from rss_to_wp.wordpress import WordPressClient

NOTICE = (
    "When this happens, it's usually because the owner only shared it with a small "
    "group of people, changed who can see it or it's been deleted."
)
INVALID_OUTPUTS = [
    {"headline": "Headline", "body": ""},
    {"headline": "Headline", "body": "<script>long text</script><p>&nbsp;</p>"},
    {"headline": "", "body": "<p>Road reopened.</p>"},
    {"headline": "Headline", "body": None},
    {"headline": None, "body": "<p>Road reopened.</p>"},
    {"headline": "Headline", "body": "<p>Road reopened.</p>", "excerpt": []},
    {"headline": "This content isn't available right now", "body": NOTICE},
    {
        "headline": "Content Unavailable Due to Privacy Settings or Deletion",
        "body": "<p>The Facebook post is unavailable.</p>",
    },
    {},
    [],
]


@pytest.mark.parametrize("output", INVALID_OUTPUTS)
@pytest.mark.parametrize("wrapped", [False, True])
def test_json_and_malformed_json_fallback_use_same_validation(output, wrapped):
    editor = OpenAIRewriter(api_key="test-only")
    text = json.dumps(output)
    if wrapped:
        text = "```json\n" + text + "\n```"
    assert editor._parse_response(text) is None


def test_malformed_json_fallback_preserves_valid_short_news():
    editor = OpenAIRewriter(api_key="test-only")
    output = {"headline": "Road reopened", "body": "<p>Main Street reopened.</p>"}
    assert editor._parse_response("```json\n" + json.dumps(output) + "\n```") == {
        **output,
        "excerpt": "",
    }


def test_direct_rewriter_blocks_platform_before_api_and_rate_limit(monkeypatch):
    editor = OpenAIRewriter(api_key="test-only")
    api = Mock()
    limit = Mock()
    monkeypatch.setattr(editor.client.chat.completions, "create", api)
    monkeypatch.setattr(editor, "_rate_limit", limit)
    assert editor.rewrite(NOTICE, "This content isn’t available right now") is None
    assert editor.rewrite(NOTICE, "Source headline") is None
    api.assert_not_called()
    limit.assert_not_called()


def test_rejected_primary_output_uses_existing_fallback_then_validates(monkeypatch):
    editor = OpenAIRewriter(api_key="test-only")
    monkeypatch.setattr(editor, "_rate_limit", lambda: None)

    def response(output):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))]
        )

    api = Mock(
        side_effect=[
            response(INVALID_OUTPUTS[0]),
            response({"headline": "Road reopened", "body": "<p>Main Street reopened.</p>"}),
        ]
    )
    monkeypatch.setattr(editor.client.chat.completions, "create", api)
    result = editor.rewrite(
        "County officials reopened Main Street after completing bridge repairs today.",
        "Source headline",
        True,
    )
    assert result["headline"] == "Source headline"
    assert [call.kwargs["model"] for call in api.call_args_list] == [
        editor.model,
        editor.fallback_model,
    ]


@pytest.mark.parametrize(
    "title,body",
    [
        ("Headline", ""),
        ("Headline", "<p>&nbsp;</p><img src='photo.jpg'>"),
        ("", "<p>Road reopened.</p>"),
        ("Headline", None),
        ("This content isn't available right now", NOTICE),
        (
            "Content Unavailable Due to Privacy Settings or Deletion",
            "<p>The Facebook post is unavailable.</p>",
        ),
        ("Headline", "<h1>Access denied</h1><p>Please try again later.</p>"),
    ],
)
def test_wp_guard_precedes_attribution_duplicate_reads_and_post(title, body):
    wp = WordPressClient("https://example.com", "test-only", "test-only")
    wp.session = Mock()
    assert wp.create_post(title, body, source_url="https://example.com/source") is None
    assert wp.session.mock_calls == []


def test_wp_guard_preserves_real_short_output_and_attribution(monkeypatch):
    wp = WordPressClient("https://example.com", "test-only", "test-only")
    wp.session = Mock()
    wp.session.get.return_value.json.return_value = []
    wp.session.post.return_value.json.return_value = {"id": 42}
    monkeypatch.setattr(wp, "_rate_limit", lambda: None)
    assert wp.create_post(
        "Road reopened", "<p>Main Street reopened.</p>", source_url="https://example.com/source"
    ) == {"id": 42}
    payload = wp.session.post.call_args.kwargs["json"]
    assert payload["content"].startswith("<p>Main Street reopened.</p>")
    assert 'href="https://example.com/source"' in payload["content"]
