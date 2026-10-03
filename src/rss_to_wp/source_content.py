"""Source text normalization shared by preflight and the rewrite guard."""

import re

MIN_SOURCE_LENGTH = 50


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
