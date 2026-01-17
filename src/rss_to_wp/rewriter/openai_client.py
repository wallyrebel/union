"""OpenAI client for AP-style article rewriting."""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from openai import OpenAI

from rss_to_wp.utils import get_logger

logger = get_logger("rewriter.openai")

# System prompt for AP-style rewriting
AP_STYLE_PROMPT = """You are a professional news editor who rewrites press releases and articles into AP (Associated Press) style news articles.

RULES:
1. Write in objective, third-person voice
2. Use short, punchy sentences and paragraphs
3. Lead with the most newsworthy information (inverted pyramid)
4. Attribute all claims to sources
5. Use active voice whenever possible
6. Avoid editorializing or adding opinions
7. Do NOT fabricate facts, quotes, or details not present in the source
8. If information is missing, do not invent it
9. Keep the article factual and concise
10. Use proper AP style for numbers, dates, titles, etc.

OUTPUT FORMAT:
You must respond with valid JSON in this exact format:
{
    "headline": "Short, compelling headline in AP style",
    "excerpt": "One to two sentence summary for preview",
    "body": "Full article body in HTML format with <p> tags for paragraphs"
}

IMPORTANT:
- The body should be 3-6 paragraphs
- Use <p> tags to wrap each paragraph
- Do NOT include the headline in the body
- Do NOT include any markdown - use HTML only
"""


class OpenAIRewriter:
    """Client for rewriting articles using OpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5-mini",
        fallback_model: str = "gpt-4.1-nano",
        max_tokens: int = 2000,
    ):
        """Initialize OpenAI rewriter.

        Args:
            api_key: OpenAI API key.
            model: Primary model to use (default: gpt-5-mini).
            fallback_model: Fallback model if primary fails (default: gpt-4.1-nano).
            max_tokens: Maximum tokens in response.
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.fallback_model = fallback_model
        self.max_tokens = max_tokens
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Ensure we don't exceed rate limits."""
        min_interval = 2.0  # 2 seconds between requests
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def rewrite(
        self,
        content: str,
        original_title: str,
        use_original_title: bool = False,
    ) -> Optional[dict]:
        """Rewrite content into AP-style article.

        Args:
            content: Original article content/HTML.
            original_title: Original article title.
            use_original_title: If True, keep the original title.

        Returns:
            Dictionary with headline, excerpt, body or None on failure.
        """
        self._rate_limit()

        # Clean HTML from content for better processing
        clean_content = self._strip_html(content)

        if not clean_content or len(clean_content) < 50:
            logger.warning("content_too_short", length=len(clean_content))
            return None

        # Truncate very long content
        if len(clean_content) > 10000:
            clean_content = clean_content[:10000] + "..."

        logger.info(
            "rewriting_article",
            title=original_title[:50],
            content_length=len(clean_content),
            model=self.model,
        )

        user_prompt = f"""Rewrite the following article into AP style:

ORIGINAL TITLE: {original_title}

ORIGINAL CONTENT:
{clean_content}

Remember to respond with valid JSON containing headline, excerpt, and body."""

        # Try primary model first, then fallback
        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        last_error = None
        for current_model in models_to_try:
            try:
                result = self._call_openai(
                    current_model, user_prompt, original_title, use_original_title
                )
                if result:
                    return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "model_failed_trying_fallback",
                    model=current_model,
                    error=str(e),
                    has_fallback=current_model != models_to_try[-1],
                )
                continue

        if last_error:
            logger.error("openai_rewrite_error", error=str(last_error))
        return None

    def _call_openai(
        self,
        model: str,
        user_prompt: str,
        original_title: str,
        use_original_title: bool,
    ) -> Optional[dict]:
        """Make the actual OpenAI API call.

        Args:
            model: Model to use for this call.
            user_prompt: The user prompt to send.
            original_title: Original article title.
            use_original_title: If True, keep the original title.

        Returns:
            Dictionary with headline, excerpt, body or None on failure.
        """
        # Build API params - use max_completion_tokens for newer models
        api_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": AP_STYLE_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }

        # Newer models (gpt-4.1, gpt-4o, gpt-5, etc.) use max_completion_tokens
        # Older models use max_tokens
        if any(x in model.lower() for x in ["4.1", "4o", "5", "o1", "o3", "o4"]):
            api_params["max_completion_tokens"] = self.max_tokens
        else:
            api_params["max_tokens"] = self.max_tokens

        # Only add response_format for models that support it
        if "o1" not in model.lower():
            api_params["response_format"] = {"type": "json_object"}

        logger.info("calling_openai", model=model)
        response = self.client.chat.completions.create(**api_params)

        # Parse response
        response_text = response.choices[0].message.content
        result = self._parse_response(response_text)

        if result:
            # Override headline if requested
            if use_original_title:
                result["headline"] = original_title

            logger.info(
                "rewrite_complete",
                model=model,
                headline=result["headline"][:50],
                body_length=len(result["body"]),
            )

            return result

        return None

    def _parse_response(self, response_text: str) -> Optional[dict]:
        """Parse the JSON response from OpenAI.

        Args:
            response_text: Raw response text.

        Returns:
            Parsed dictionary or None.
        """
        try:
            data = json.loads(response_text)

            # Validate required fields
            if not all(k in data for k in ["headline", "body"]):
                logger.warning("missing_required_fields", data=data)
                return None

            return {
                "headline": data["headline"].strip(),
                "excerpt": data.get("excerpt", "").strip(),
                "body": data["body"].strip(),
            }

        except json.JSONDecodeError as e:
            logger.warning("json_parse_error", error=str(e), response=response_text[:200])

            # Try to extract from malformed response
            return self._extract_fallback(response_text)

    def _extract_fallback(self, text: str) -> Optional[dict]:
        """Try to extract content from malformed response.

        Args:
            text: Response text that failed JSON parsing.

        Returns:
            Extracted dictionary or None.
        """
        try:
            # Try to find JSON-like content
            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass

        logger.warning("fallback_extraction_failed")
        return None

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags and clean up content.

        Args:
            html: HTML content.

        Returns:
            Plain text content.
        """
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


def rewrite_with_openai(
    content: str,
    original_title: str,
    api_key: str,
    model: str = "gpt-5-mini",
    fallback_model: str = "gpt-4.1-nano",
    use_original_title: bool = False,
) -> Optional[dict]:
    """Convenience function to rewrite content.

    Args:
        content: Original article content.
        original_title: Original title.
        api_key: OpenAI API key.
        model: Primary model to use.
        fallback_model: Fallback model if primary fails.
        use_original_title: Keep original title if True.

    Returns:
        Dictionary with headline, excerpt, body or None.
    """
    rewriter = OpenAIRewriter(api_key=api_key, model=model, fallback_model=fallback_model)
    return rewriter.rewrite(content, original_title, use_original_title)
