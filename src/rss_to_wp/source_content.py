"""Visible-text and platform-placeholder checks for input and publication."""

from __future__ import annotations

import re

MIN_SOURCE_LENGTH = 50

# Match interface headings as whole headings, not keywords in real news about
# outages, privacy, deleted posts or login changes.
_PLATFORM_HEADING = re.compile(
    r"(?:this (?:content|page|post|video) (?:isn't|is not) available(?: right now)?"
    r"|(?:sorry,? )?(?:this )?page (?:isn't|is not) available"
    r"|(?:content|page|post|video) (?:unavailable|not available|not found)"
    r"|content unavailable due to (?:privacy settings|deletion|privacy settings or deletion)"
    r"|(?:log ?in|sign in)(?: to (?:facebook|instagram|continue|view (?:this (?:post|content)|more)))?"
    r"|(?:facebook [-\u2013] )?log in or sign up|log into facebook|you must log in to continue"
    r"|(?:sorry,? )?something went wrong|access denied|temporarily unavailable|(?:503 )?service unavailable"
    r"|(?:403 )?forbidden|(?:404 )?page not found|404 not found"
    r"|(?:500 )?internal server error|(?:429 )?too many requests)"
)

# The confirmed 139-character Facebook notice can arrive without its heading.
_FACEBOOK_NOTICE = (
    "when this happens, it's usually because the owner only shared it with a small "
    "group of people, changed who can see it or it's been deleted"
)

# Only known interface continuations may follow a heading. This avoids treating
# an article that quotes an error message and then reports news as an error page.
_PLATFORM_CONTINUATION = re.compile(
    r"(?:"
    + re.escape(_FACEBOOK_NOTICE)
    + r"|the link you followed may be broken,? or the page may have been removed[.!]?"
    r"|(?:please )?(?:log ?in|sign in) to (?:continue|view this (?:post|content))[.!]?"
    r"|(?:please )?try again(?: later)?[.!]?"
    r"|go back|go to (?:news feed|facebook)|return to (?:home|facebook))"
)


def _normalized_text(value: str) -> str:
    return clean_source_content(value).casefold().replace("\u2019", "'").strip(' .!?:"\u201c\u201d')


def platform_placeholder_reason(title: str, content: str) -> str | None:
    """Identify known access/error UI, without broad privacy/error keyword bans."""
    heading = _normalized_text(title)
    text = _normalized_text(content)
    if _PLATFORM_HEADING.fullmatch(heading):
        return "platform_heading"
    if text == _FACEBOOK_NOTICE:
        return "facebook_unavailable_notice"
    if re.fullmatch(
        r"(?:log ?in|sign in) to (?:facebook|instagram) to "
        r"(?:view this (?:post|content)|continue)(?: and continue browsing)?",
        text,
    ):
        return "platform_login_notice"
    if _PLATFORM_HEADING.fullmatch(text):
        return "platform_notice"
    match = _PLATFORM_HEADING.match(text)
    if match:
        continuation = text[match.end() :].lstrip(" .!?:")
        if _PLATFORM_CONTINUATION.fullmatch(continuation):
            return "platform_notice"
    return None


def publication_content_problem(title: str, content: str) -> str | None:
    """Reject missing/empty output and known placeholders before any WP work.

    No output length floor: substantive short news remains publishable.
    """
    if not isinstance(title, str) or not isinstance(content, str):
        return "invalid_output_fields"
    if not clean_source_content(title):
        return "empty_headline"
    if not clean_source_content(content):
        return "empty_body"
    return platform_placeholder_reason(title, content)


def clean_source_content(html: str) -> str:
    """Return the same visible text used to decide rewrite eligibility."""
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get text
        text = soup.get_text(separator=" ")

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        return text

    except Exception:
        # Fallback: simple regex
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
