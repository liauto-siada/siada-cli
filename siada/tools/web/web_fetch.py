"""
Web fetch tool (local fallback)

Uses trafilatura library to fetch web content with Playwright fallback for JS-rendered pages.
This module serves as a local fallback for web_fetch when the internal package is not available.
"""

WEB_FETCH_DOCS = """Web content fetching tool for retrieving and extracting content from web pages
* Uses trafilatura library to intelligently extract clean content from web pages
* Automatically falls back to Playwright (headless browser) for JavaScript-rendered pages (SPA)
* Supports multiple output formats: text, markdown, JSON, and raw HTML
* Handles various web page types including articles, blogs, documentation, and news sites
* Automatically validates URLs and provides detailed error messages for troubleshooting
* Returns structured observation objects with success status and extracted content

SUPPORTED OUTPUT FORMATS:
- `text`: Clean plain text content without HTML tags (default)
- `markdown`: Content formatted as Markdown with preserved structure
- `json`: Structured JSON format with metadata including title, author, date, etc.
- `html`: Raw HTML content as downloaded from the source

USAGE GUIDELINES:

Before using this tool:
1. Ensure the target URL is accessible and contains the content you need
2. Choose the appropriate output format based on your use case:
   - Use `text` for simple content analysis or when you need clean readable text
   - Use `markdown` when you need to preserve document structure and formatting
   - Use `json` when you need metadata along with content (title, publication date, etc.)
   - Use `html` when you need the raw source code for further processing

When using this tool:
1. Always provide a complete, valid URL including the protocol (http:// or https://)
2. The tool will automatically validate the URL format before attempting to fetch content
3. If the request fails, check the error message for specific details about the failure
4. Large pages may take some time to process, especially when extracting to JSON format

COMMON USE CASES:
- Research: Extract article content from news sites, blogs, or documentation
- Content Analysis: Get clean text for sentiment analysis or keyword extraction
- Documentation: Convert web pages to markdown for documentation purposes
- Data Collection: Extract structured data from web pages in JSON format
- Web Scraping: Get raw HTML for custom parsing and data extraction

ERROR HANDLING:
The tool provides detailed error messages for common issues:
- Invalid URL format: Check that the URL includes protocol and domain
- Network request failed: Check internet connection and URL accessibility
- Unable to download content: The target page may be protected or unavailable
- Unable to extract content: The page structure may not be supported by trafilatura
- JSON parsing failed: The extracted content could not be formatted as valid JSON

EXAMPLES:
- web_fetch(url="https://example.com/article", format="text")
- web_fetch(url="https://docs.example.com/guide", format="markdown")
- web_fetch(url="https://news.example.com/story", format="json")
- web_fetch(url="https://example.com/page", format="html")

Args:
    context: Runtime context wrapper for the agent
    url: Complete URL of the webpage to fetch (must include protocol)
    format: Output format - "text", "markdown", "json", or "html" (default: "text")

Returns:
    WebFetchObservation: Object containing the fetch results with success status and content
"""
import json
import logging
from typing import Literal, Optional
import trafilatura
from urllib.parse import urlparse
from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.global_cache import set_global_cache, get_global_cache
from siada.tools.coder.observation.observation import FunctionCallResult

logger = logging.getLogger(__name__)

# Minimum content length threshold to consider extraction successful.
# If trafilatura returns less than this, we fall back to Playwright.
MIN_CONTENT_LENGTH = 500

# Max content length limit (200000 characters)
MAX_CONTENT_LENGTH = 200_000

# Max scroll steps when triggering lazy-loaded content
_MAX_SCROLL_STEPS = 5

# Pause between scroll steps (ms)
_SCROLL_PAUSE_MS = 800

# SPA framework markers that indicate JS rendering is likely needed
_SPA_MARKERS = ('id="root"', 'id="__next"', 'id="app"')

# Minimum text-to-HTML ratio to consider extraction meaningful
_MIN_TEXT_DENSITY = 0.05

# Cache key prefix for URL-level fetch caching
_CACHE_PREFIX = "web_fetch:"


def _apply_stealth(page) -> None:
    """
    Apply stealth patches to a Playwright page to bypass common bot-detection
    (e.g. Cloudflare, Akamai).  Uses playwright-stealth when available, otherwise
    falls back to a minimal set of JS overrides.
    """
    try:
        from playwright_stealth import stealth_sync  # type: ignore
        stealth_sync(page)
        return
    except ImportError:
        pass

    # Minimal stealth: hide webdriver flag and patch navigator properties
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        window.chrome = { runtime: {} };
    """)


def _is_low_quality(text: str, html: str) -> bool:
    """
    Determine whether extracted text is low-quality and Playwright fallback is needed.

    Checks content length, SPA framework markers, and text-to-HTML density ratio
    to avoid unnecessary Playwright launches on valid short pages, while catching
    JS-rendered SPAs that trafilatura cannot handle.
    """
    if not text or len(text.strip()) < MIN_CONTENT_LENGTH:
        return True

    # Detect SPA framework markers in raw HTML
    if html and any(marker in html for marker in _SPA_MARKERS):
        return True

    # Low text density indicates most content is in tags/scripts, not real text
    if html and len(text) / max(len(html), 1) < _MIN_TEXT_DENSITY:
        return True

    return False


def _scroll_to_bottom(page, max_steps: int = _MAX_SCROLL_STEPS, pause: int = _SCROLL_PAUSE_MS) -> None:
    """
    Smart scroll: incrementally scroll the page and stop early when page height
    stops changing, avoiding unnecessary waits on static pages.
    """
    prev_height = 0
    for _ in range(max_steps):
        height = page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause)
        prev_height = height
    # Scroll back to top so full DOM is accessible
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)


def _fetch_with_playwright(url: str, timeout: int = 60000) -> Optional[str]:
    """
    Fetch page HTML using Playwright headless browser for JS-rendered pages.

    Args:
        url: URL to fetch
        timeout: Page load timeout in milliseconds

    Returns:
        Rendered HTML string, or None if Playwright is unavailable or fetch fails
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed, skipping JS rendering fallback")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 900},
                    locale="en-US",
                    timezone_id="America/New_York",
                )
                try:
                    page = ctx.new_page()

                    # Apply stealth patches before navigation
                    _apply_stealth(page)

                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                    # Smart wait: prefer networkidle, but cap at 15s so we don't hang
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass

                    # Wait for meaningful content selectors (common in doc sites / SPAs)
                    _content_selectors = [
                        "main",
                        "article",
                        "[role='main']",
                        "#content",
                        ".content",
                        ".markdown-body",
                        ".docs-content",
                    ]
                    for selector in _content_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=5000)
                            break
                        except Exception:
                            continue

                    # Scroll to trigger lazy-loaded content
                    _scroll_to_bottom(page)

                    # Final short wait for any post-scroll rendering
                    page.wait_for_timeout(1500)

                    html = page.content()
                    return html
                finally:
                    ctx.close()
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"Playwright fetch failed for {url}: {e}")
        return None


def _extract_content(html: str, output_format: str) -> Optional[str]:
    """
    Extract content from HTML using trafilatura.

    Args:
        html: Raw HTML content
        output_format: Desired output format

    Returns:
        Extracted content string, or None if extraction fails
    """
    if output_format == "html":
        return html
    elif output_format == "text":
        return trafilatura.extract(
            html, output_format='txt',
            include_tables=True,
            favor_recall=True,
        )
    elif output_format == "markdown":
        return trafilatura.extract(
            html, output_format='markdown',
            include_tables=True, include_links=True,
            favor_recall=True,
        )
    elif output_format == "json":
        extracted_data = trafilatura.extract(
            html,
            output_format='json',
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=True,
            favor_recall=True,
        )
        if extracted_data:
            json_data = json.loads(extracted_data)
            return json.dumps(json_data, ensure_ascii=False, indent=2)
        return None
    return None


class WebFetchObservation(FunctionCallResult):
    """Web fetch result observation"""

    def __init__(self, url: str, content: str, format: str, success: bool = True, error: str = None):
        self.url = url
        self.content = content
        self.format = format
        self.success = success
        self.error = error

    def __str__(self) -> str:
        if not self.success:
            return f"Web fetch failed ({self.url}): {self.error}"

        content_preview = self.content[:200] + "..." if len(self.content) > 200 else self.content
        return f"Web fetch successful ({self.url}, format: {self.format}):\n{content_preview}"


@function_tool(name_override="web_fetch",
               description_override=WEB_FETCH_DOCS)
def web_fetch(
        context: RunContextWrapper[CodeAgentContext],
        url: str,
        output_format: Literal["markdown", "text", "json", "html"] = "text"
) -> WebFetchObservation:
    """
    Fetch web content and return content in specified format.

    Strategy:
    1. Try trafilatura (fast, no browser overhead)
    2. If content is too short (likely a JS-rendered SPA), fall back to Playwright
    3. Always pick the longer extraction between trafilatura and Playwright

    Args:
        context: Runtime context wrapper
        url: URL of the webpage to fetch
        format: Output format, supports "markdown", "text", "json", "html"

    Returns:
        WebFetchObservation: Observation object containing fetch results
    """
    try:
        # Validate URL format
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return WebFetchObservation(
                url=url,
                content="",
                format=output_format,
                success=False,
                error=f"Invalid URL format: {url}"
            )

        # Check URL-level cache to avoid redundant fetches within the same session
        cache_key = f"{_CACHE_PREFIX}{url}:{output_format}"
        cached_result = get_global_cache(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for: {cache_key}")
            return cached_result

        # Step 1: Try trafilatura (lightweight, no JS rendering)
        downloaded = trafilatura.fetch_url(url)
        extracted = None
        used_playwright = False

        if downloaded:
            extracted = _extract_content(downloaded, output_format)

        trafilatura_len = len(extracted.strip()) if extracted else 0

        # Step 2: If trafilatura result is low-quality, try Playwright fallback
        needs_fallback = not extracted or (
            output_format != "html" and _is_low_quality(extracted, downloaded or "")
        )
        if needs_fallback:
            logger.info(
                f"Trafilatura extracted insufficient content ({trafilatura_len} chars), "
                f"trying Playwright fallback for: {url}"
            )
            playwright_html = _fetch_with_playwright(url)
            if playwright_html:
                playwright_extracted = _extract_content(playwright_html, output_format)
                playwright_len = len(playwright_extracted.strip()) if playwright_extracted else 0
                if playwright_len > trafilatura_len:
                    extracted = playwright_extracted
                    used_playwright = True
                    logger.info(
                        f"Playwright yielded more content ({playwright_len} chars vs "
                        f"trafilatura {trafilatura_len} chars) for: {url}"
                    )

        if not extracted:
            return WebFetchObservation(
                url=url,
                content="",
                format=output_format,
                success=False,
                error=f"Unable to extract content from webpage: {url}"
            )

        # Truncate content if it exceeds max length
        if len(extracted) > MAX_CONTENT_LENGTH:
            extracted = extracted[:MAX_CONTENT_LENGTH] + "\n\n... [Content truncated]"

        if used_playwright:
            logger.info(f"Successfully fetched content using Playwright for: {url}")

        result = WebFetchObservation(
            url=url,
            content=extracted,
            format=output_format,
            success=True
        )

        # Store successful result in cache for subsequent calls
        set_global_cache(cache_key, result)

        return result

    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing failed: {str(e)}"
        return WebFetchObservation(
            url=url,
            content="",
            format=output_format,
            success=False,
            error=error_msg
        )
    except Exception as e:
        error_msg = f"Web fetch failed: {str(e)}"
        return WebFetchObservation(
            url=url,
            content="",
            format=output_format,
            success=False,
            error=error_msg
        )
