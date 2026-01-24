"""
Web Crawler module for the Web-to-PDF Documentation Crawler.

This module implements the core crawling logic with:
- Recursive page discovery following internal links
- Navigation-aware ordering to maintain document structure
- State management to prevent infinite loops
- Respectful crawling with rate limiting
- Playwright support for JavaScript-rendered pages
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple
from collections import OrderedDict
from contextlib import contextmanager

import requests
from bs4 import BeautifulSoup, Tag

# Playwright is optional - will be used if available
try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from config import CrawlerConfig
from url_utils import (
    normalize_url,
    resolve_url,
    is_valid_doc_url,
    is_same_domain,
    get_url_depth,
    URLTracker,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class CrawledPage:
    """
    Represents a crawled documentation page.

    Attributes:
        url: The normalized URL of the page.
        title: The page title extracted from <title> or <h1>.
        html_content: The raw HTML content of the page.
        extracted_content: The main content HTML (without navigation, etc.).
        order_index: The order in which this page should appear in the PDF.
        depth: The depth of this page from the root URL.
    """
    url: str
    title: str
    html_content: str
    extracted_content: str
    order_index: int = 0
    depth: int = 0


class NavigationExtractor:
    """
    Extract and parse navigation structure from documentation pages.

    This class identifies the navigation menu/sidebar and extracts
    the logical ordering of documentation pages.
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the navigation extractor.

        Args:
            config: The crawler configuration containing nav selectors.
        """
        self.config = config

    def find_navigation(self, soup: BeautifulSoup) -> Optional[Tag]:
        """
        Find the navigation element in the page.

        Tries multiple selectors in order of preference.

        Args:
            soup: The parsed HTML document.

        Returns:
            The navigation element if found, None otherwise.
        """
        for selector in self.config.nav_selectors:
            nav = soup.select_one(selector)
            if nav:
                return nav
        return None

    def extract_nav_links(
        self, soup: BeautifulSoup, current_url: str
    ) -> List[str]:
        """
        Extract ordered links from the navigation menu.

        These links represent the logical reading order of the documentation.

        Args:
            soup: The parsed HTML document.
            current_url: The URL of the current page for resolving relative links.

        Returns:
            A list of absolute URLs in navigation order.
        """
        nav = self.find_navigation(soup)
        if not nav:
            return []

        ordered_links = []
        seen_urls: Set[str] = set()

        # Find all links within the navigation
        for anchor in nav.find_all("a", href=True):
            href = anchor.get("href", "")
            resolved = resolve_url(href, current_url)

            if resolved and resolved not in seen_urls:
                # Only include internal links
                if is_same_domain(resolved, self.config.base_url):
                    normalized = normalize_url(resolved)
                    if normalized not in seen_urls:
                        ordered_links.append(normalized)
                        seen_urls.add(normalized)

        return ordered_links


class ContentExtractor:
    """
    Extract the main content from documentation pages.

    Removes navigation, headers, footers, and other non-content elements
    to produce clean HTML suitable for PDF conversion.
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the content extractor.

        Args:
            config: The crawler configuration containing content selectors.
        """
        self.config = config

    def extract_title(self, soup: BeautifulSoup) -> str:
        """
        Extract the page title.

        Tries multiple sources in order of preference:
        1. The first <h1> tag
        2. The <title> tag
        3. "Untitled" as fallback

        Args:
            soup: The parsed HTML document.

        Returns:
            The extracted page title.
        """
        # Try h1 first (usually more specific to the page content)
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)

        # Fall back to title tag
        title = soup.find("title")
        if title and title.get_text(strip=True):
            return title.get_text(strip=True)

        return "Untitled"

    def extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        Extract the main documentation content from the page.

        Tries multiple content selectors and returns the first match.
        If no specific content area is found, returns the body content
        with navigation elements removed.

        Args:
            soup: The parsed HTML document.

        Returns:
            HTML string of the main content.
        """
        # Try each content selector in order
        for selector in self.config.content_selectors:
            content = soup.select_one(selector)
            if content:
                # Remove any nested navigation elements
                self._remove_nav_elements(content)
                return str(content)

        # Fallback: use body with nav elements removed
        body = soup.find("body")
        if body:
            # Create a copy to avoid modifying the original
            body_copy = BeautifulSoup(str(body), "html.parser").find("body")
            if body_copy:
                self._remove_nav_elements(body_copy)
                return str(body_copy)

        return ""

    def _remove_nav_elements(self, element: Tag) -> None:
        """
        Remove navigation and non-content elements from an element.

        Modifies the element in place.

        Args:
            element: The BeautifulSoup element to clean.
        """
        # Elements to remove
        remove_selectors = [
            "nav",
            "header",
            "footer",
            ".sidebar",
            ".navigation",
            ".toc",
            ".breadcrumb",
            ".edit-link",
            ".page-nav",
            ".footer",
            ".header",
            "script",
            "style",
            "noscript",
            "[role='navigation']",
            ".edit-this-page",
            ".last-updated",
        ]

        for selector in remove_selectors:
            for elem in element.select(selector):
                elem.decompose()


class DocumentationCrawler:
    """
    Main crawler class that orchestrates the documentation crawling process.

    This class:
    1. Starts from the base URL and discovers all internal pages
    2. Maintains visit state to prevent infinite loops
    3. Respects rate limits and server load
    4. Extracts content and navigation structure
    5. Returns pages in logical reading order
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the documentation crawler.

        Args:
            config: The crawler configuration.
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(config.get_headers())
        self.url_tracker = URLTracker()
        self.nav_extractor = NavigationExtractor(config)
        self.content_extractor = ContentExtractor(config)

        # Store pages with their content
        self.pages: Dict[str, CrawledPage] = OrderedDict()

        # Track navigation order across all pages
        self.nav_order: Dict[str, int] = {}
        self._order_counter = 0

    def crawl(self) -> List[CrawledPage]:
        """
        Start the crawling process from the base URL.

        Returns:
            A list of CrawledPage objects in logical reading order.
        """
        logger.info(f"Starting crawl from: {self.config.base_url}")

        # Begin with the base URL
        base_normalized = normalize_url(self.config.base_url)
        self._crawl_page(base_normalized, depth=0)

        # Sort pages by their navigation order
        sorted_pages = sorted(
            self.pages.values(),
            key=lambda p: (p.order_index, p.depth, p.url)
        )

        logger.info(f"Crawl complete. Found {len(sorted_pages)} pages.")
        return sorted_pages

    def _crawl_page(self, url: str, depth: int) -> None:
        """
        Crawl a single page and discover linked pages.

        This method:
        1. Fetches the page content
        2. Extracts navigation links for ordering
        3. Extracts main content
        4. Recursively crawls discovered internal links

        Args:
            url: The URL to crawl.
            depth: The current crawl depth.
        """
        # Check depth limit
        if depth > self.config.max_depth:
            logger.debug(f"Skipping {url} - max depth exceeded")
            return

        # Check if already visited
        if self.url_tracker.is_visited(url):
            return

        # Mark as visited
        self.url_tracker.mark_visited(url)
        logger.info(f"Crawling ({depth}): {url}")

        # Fetch the page
        html_content = self._fetch_page(url)
        if not html_content:
            return

        # Parse the HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Assign navigation order
        if url not in self.nav_order:
            self.nav_order[url] = self._order_counter
            self._order_counter += 1

        # Extract page data
        title = self.content_extractor.extract_title(soup)
        main_content = self.content_extractor.extract_main_content(soup)

        # Store the page
        self.pages[url] = CrawledPage(
            url=url,
            title=title,
            html_content=html_content,
            extracted_content=main_content,
            order_index=self.nav_order[url],
            depth=depth,
        )

        # Extract navigation links first (these define the reading order)
        if self.config.follow_nav_order:
            nav_links = self.nav_extractor.extract_nav_links(soup, url)
            for nav_url in nav_links:
                if nav_url not in self.nav_order:
                    self.nav_order[nav_url] = self._order_counter
                    self._order_counter += 1

        # Find all links on the page for crawling
        discovered_urls = self._extract_links(soup, url)

        # Respect rate limiting
        time.sleep(self.config.request_delay)

        # Recursively crawl discovered pages
        for discovered_url in discovered_urls:
            if self.url_tracker.should_visit(discovered_url):
                url_depth = get_url_depth(discovered_url, self.config.base_url)
                self._crawl_page(discovered_url, depth=url_depth)

    def _fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch a page's HTML content.

        Args:
            url: The URL to fetch.

        Returns:
            The HTML content as a string, or None if fetch failed.
        """
        try:
            response = self.session.get(
                url,
                timeout=self.config.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                logger.debug(f"Skipping non-HTML content: {url}")
                return None

            return response.text

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def _extract_links(self, soup: BeautifulSoup, current_url: str) -> List[str]:
        """
        Extract all valid internal links from a page.

        Filters out external links and applies exclusion patterns.

        Args:
            soup: The parsed HTML document.
            current_url: The URL of the current page.

        Returns:
            A list of valid internal URLs to crawl.
        """
        links = []
        seen: Set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            resolved = resolve_url(href, current_url)

            if not resolved:
                continue

            normalized = normalize_url(resolved)

            # Skip if already seen in this extraction
            if normalized in seen:
                continue
            seen.add(normalized)

            # Validate the URL
            if is_valid_doc_url(
                normalized,
                self.config.base_url,
                self.config.excluded_patterns
            ):
                links.append(normalized)

        return links

    def get_stats(self) -> Dict[str, int]:
        """
        Get crawling statistics.

        Returns:
            Dictionary with crawl statistics.
        """
        return {
            "pages_crawled": len(self.pages),
            "urls_visited": self.url_tracker.visited_count,
            "max_depth_reached": max(
                (p.depth for p in self.pages.values()), default=0
            ),
        }


class PlaywrightCrawler(DocumentationCrawler):
    """
    Crawler that uses Playwright for JavaScript-rendered pages.

    This crawler extends DocumentationCrawler to handle sites that
    require JavaScript execution to render content, such as those
    built with React, Vue, or MkDocs Material theme.
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the Playwright-based crawler.

        Args:
            config: The crawler configuration.
        """
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._context = None
        self._playwright = None

    def crawl(self) -> List[CrawledPage]:
        """
        Start the crawling process using Playwright.

        Returns:
            A list of CrawledPage objects in logical reading order.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available. Install with: pip install playwright && playwright install chromium")
            return []

        logger.info(f"Starting Playwright crawl from: {self.config.base_url}")
        logger.info("Using headless browser for JavaScript-rendered content...")

        with sync_playwright() as playwright:
            self._playwright = playwright
            self._browser = playwright.chromium.launch(headless=True)

            # Create browser context with realistic settings
            self._context = self._browser.new_context(
                user_agent=self.config.user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )

            try:
                # Begin with the base URL
                base_normalized = normalize_url(self.config.base_url)
                self._crawl_page(base_normalized, depth=0)
            finally:
                if self._context:
                    self._context.close()
                if self._browser:
                    self._browser.close()

        # Sort pages by their navigation order
        sorted_pages = sorted(
            self.pages.values(),
            key=lambda p: (p.order_index, p.depth, p.url)
        )

        logger.info(f"Crawl complete. Found {len(sorted_pages)} pages.")
        return sorted_pages

    def _fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch a page's HTML content using Playwright.

        This method waits for JavaScript to render the page content
        before extracting the HTML.

        Args:
            url: The URL to fetch.

        Returns:
            The rendered HTML content as a string, or None if fetch failed.
        """
        if not self._context:
            return None

        try:
            page = self._context.new_page()

            try:
                # Navigate to the page
                page.goto(url, wait_until="networkidle", timeout=self.config.timeout * 1000)

                # Wait for content to render (give JS time to execute)
                page.wait_for_timeout(2000)

                # Try to wait for common content indicators
                try:
                    page.wait_for_selector("main, article, .content, .md-content", timeout=5000)
                except Exception:
                    pass  # Continue even if selector not found

                # Get the rendered HTML
                html_content = page.content()

                return html_content

            finally:
                page.close()

        except Exception as e:
            logger.warning(f"Failed to fetch {url} with Playwright: {e}")
            return None


def create_crawler(config: CrawlerConfig, use_javascript: bool = False) -> DocumentationCrawler:
    """
    Factory function to create the appropriate crawler.

    Args:
        config: The crawler configuration.
        use_javascript: If True, use Playwright for JS-rendered pages.

    Returns:
        A DocumentationCrawler instance (either standard or Playwright-based).
    """
    if use_javascript:
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available, falling back to standard crawler")
            return DocumentationCrawler(config)
        return PlaywrightCrawler(config)
    return DocumentationCrawler(config)
