"""
Configuration module for the Web-to-PDF Documentation Crawler.

This module contains all configurable settings for the crawler including
the base URL, output filename, and crawling parameters.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CrawlerConfig:
    """
    Configuration settings for the documentation crawler.

    Attributes:
        base_url: The root URL of the documentation site to crawl.
        output_filename: The name of the final merged PDF file.
        max_depth: Maximum recursion depth for crawling (prevents infinite loops).
        request_delay: Delay between requests in seconds (be respectful to servers).
        timeout: Request timeout in seconds.
        user_agent: Custom user agent string for HTTP requests.
        excluded_patterns: URL patterns to exclude from crawling.
        included_extensions: File extensions to include (empty means all HTML pages).
        follow_nav_order: Attempt to follow navigation/sidebar ordering.
    """

    # Primary configuration
    base_url: str = "https://docs.example.com"
    output_filename: str = "documentation.pdf"

    # Crawling behavior
    max_depth: int = 10
    request_delay: float = 0.5
    timeout: int = 30

    # HTTP settings - use realistic browser User-Agent to avoid blocks
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # URL filtering
    excluded_patterns: List[str] = field(default_factory=lambda: [
        "/api/",
        "/changelog",
        "/releases",
        "/_static/",
        "/_images/",
        ".zip",
        ".tar.gz",
        ".exe",
        ".dmg",
    ])

    # Only crawl pages with these extensions (empty list = all HTML pages)
    included_extensions: List[str] = field(default_factory=lambda: [
        "",  # No extension (common for clean URLs)
        ".html",
        ".htm",
        "/",  # Directory-style URLs
    ])

    # Navigation ordering
    follow_nav_order: bool = True
    nav_selectors: List[str] = field(default_factory=lambda: [
        "nav",
        ".sidebar",
        ".toc",
        ".navigation",
        "[role='navigation']",
        ".menu",
        "#sidebar",
        ".docs-sidebar",
        ".table-of-contents",
    ])

    # Content extraction selectors (in order of preference)
    content_selectors: List[str] = field(default_factory=lambda: [
        "main",
        "article",
        ".content",
        ".main-content",
        ".documentation",
        "#content",
        ".markdown-body",
        ".doc-content",
        "[role='main']",
    ])

    # PDF generation settings
    pdf_page_size: str = "A4"
    pdf_margin: str = "2cm"

    def get_headers(self) -> dict:
        """Return HTTP headers for requests."""
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }


# Default configuration instance
default_config = CrawlerConfig()
