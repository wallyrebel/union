"""Reject observed replacement-model placeholders without suppressing short news."""
import json
from unittest.mock import Mock
import pytest
from rss_to_wp.rewriter import OpenAIRewriter
from rss_to_wp.source_content import publication_content_problem
from rss_to_wp.wordpress import WordPressClient

BAD = [
    ("No Schedule Details Provided for NAHS Athletics", "An announcement about NAHS athletics encourages fans to support the Bulldogs this week. It does not provide a schedule, event dates or times."),
    ("No Conference Details Provided", "The submitted text asks Kelvin what he wants to learn to do at a conference but does not include his response."),
    ("Article Offers No Details on Kelvin’s Community Work", "The supplied text asks Kelvin how he has helped his community in the past but does not include an answer."),
    ("Conference question", "The provided content does not provide the interviewee's answer."),
]

@pytest.mark.parametrize("headline,body", BAD)
def test_placeholder_rejected_by_parser_and_wordpress_boundary(headline, body):
    assert publication_content_problem(headline, body) == "model_missing_source_details"
    editor = OpenAIRewriter(api_key="offline-test")
    payload={"headline":headline,"body":"<p>"+body+"</p>"}
    assert editor._parse_response(json.dumps(payload)) is None
    wp=WordPressClient("https://example.invalid", "offline-test", "offline-test")
    wp.session=Mock()
    assert wp.create_post(headline,payload["body"],source_url="https://example.invalid/source") is None
    assert wp.session.mock_calls == []

@pytest.mark.parametrize("headline,body", [
    ("Road reopened", "Main Street reopened."),
    ("Officials give no details about investigation", "Police declined to release details about the investigation Monday."),
    ("Conference schedule released", "The conference opens at 9 a.m. Tuesday."),
    ("NAHS athletics seeks community support", "NAHS athletics encouraged fans to support the Bulldogs this week."),
])
def test_substantive_short_news_and_reporting_about_missing_details_survive(headline,body):
    assert publication_content_problem(headline,body) is None
