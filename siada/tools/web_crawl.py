"""
Web content crawling tool

Uses trafilatura library to fetch web content, supports multiple output formats
"""

WEB_CRAWL_DOCS = """Web content crawling tool for fetching and extracting content from web pages
* Uses trafilatura library to intelligently extract clean content from web pages
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
- web_crawl(url="https://example.com/article", format="text")
- web_crawl(url="https://docs.example.com/guide", format="markdown")
- web_crawl(url="https://news.example.com/story", format="json")
- web_crawl(url="https://example.com/page", format="html")

Args:
    context: Runtime context wrapper for the agent
    url: Complete URL of the webpage to crawl (must include protocol)
    format: Output format - "text", "markdown", "json", or "html" (default: "text")

Returns:
    WebCrawlObservation: Object containing the crawling results with success status and content
"""
import json
import logging
from typing import Literal
import trafilatura
import requests
from urllib.parse import urlparse
from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult


class WebCrawlObservation(FunctionCallResult):
    """Web crawling result observation"""

    def __init__(self, url: str, content: str, format: str, success: bool = True, error: str = None):
        self.url = url
        self.content = content
        self.format = format
        self.success = success
        self.error = error

    def __str__(self) -> str:
        if not self.success:
            return f"Web crawling failed ({self.url}): {self.error}"

        content_preview = self.content[:200] + "..." if len(self.content) > 200 else self.content
        return f"Web crawling successful ({self.url}, format: {self.format}):\n{content_preview}"


@function_tool(name_override="web_crawl",
               description_override="Complete the bug fix task and mark it as finished. This tool MUST be called to properly complete any bug fix task. Failure to call this tool means the bug fix task is incomplete and unacceptable."
               )
def web_crawl(
        context: RunContextWrapper[CodeAgentContext],
        url: str,
        format: Literal["markdown", "text", "json", "html"] = "text"
) -> WebCrawlObservation:
    """
    Crawl web content and return content in specified format
    
    Args:
        context: Runtime context wrapper
        url: URL of the webpage to crawl
        format: Output format, supports "markdown", "text", "json", "html"
        
    Returns:
        WebCrawlObservation: Observation object containing crawling results
    """
    try:
        # Validate URL format
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return WebCrawlObservation(
                url=url,
                content="",
                format=format,
                success=False,
                error=f"Invalid URL format: {url}"
            )

        # Download web content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return WebCrawlObservation(
                url=url,
                content="",
                format=format,
                success=False,
                error=f"Unable to download web content: {url}"
            )

        if format == "html":
            extracted = downloaded
        elif format == "text":
            extracted = trafilatura.extract(downloaded, output_format='txt')
        elif format == "markdown":
            extracted = trafilatura.extract(downloaded, output_format='markdown')
        elif format == "json":
            extracted_data = trafilatura.extract(
                downloaded,
                output_format='json',
                include_comments=False,
                include_tables=True,
                include_images=True
            )
            if extracted_data:
                # Parse JSON and reformat
                json_data = json.loads(extracted_data)
                extracted = json.dumps(json_data, ensure_ascii=False, indent=2)
            else:
                extracted = None
        else:
            return WebCrawlObservation(
                url=url,
                content="",
                format=format,
                success=False,
                error=f"Unsupported format: {format}"
            )

        if not extracted:
            return WebCrawlObservation(
                url=url,
                content="",
                format=format,
                success=False,
                error=f"Unable to extract content from webpage: {url}"
            )

        return WebCrawlObservation(
            url=url,
            content=extracted,
            format=format,
            success=True
        )

    except requests.exceptions.RequestException as e:
        error_msg = f"Network request failed: {str(e)}"
        return WebCrawlObservation(
            url=url,
            content="",
            format=format,
            success=False,
            error=error_msg
        )
    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing failed: {str(e)}"
        return WebCrawlObservation(
            url=url,
            content="",
            format=format,
            success=False,
            error=error_msg
        )
    except Exception as e:
        error_msg = f"Web crawling failed: {str(e)}"
        return WebCrawlObservation(
            url=url,
            content="",
            format=format,
            success=False,
            error=error_msg
        )
