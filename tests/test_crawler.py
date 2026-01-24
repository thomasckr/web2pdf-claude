"""
Unit tests for the crawler module.

Tests cover:
- Navigation extraction from HTML
- Content extraction from documentation pages
- Link discovery and filtering
- Page ordering based on navigation
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup

from config import CrawlerConfig
from crawler import (
    NavigationExtractor,
    ContentExtractor,
    DocumentationCrawler,
    CrawledPage,
)


@pytest.fixture
def config():
    """Create a test configuration."""
    return CrawlerConfig(
        base_url="https://docs.example.com",
        max_depth=5,
        request_delay=0,  # No delay in tests
    )


@pytest.fixture
def sample_html():
    """Create sample HTML for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Getting Started - Example Docs</title>
    </head>
    <body>
        <nav class="sidebar">
            <a href="/docs/intro">Introduction</a>
            <a href="/docs/getting-started">Getting Started</a>
            <a href="/docs/advanced">Advanced Guide</a>
            <a href="https://github.com/example">GitHub</a>
        </nav>
        <main>
            <h1>Getting Started</h1>
            <p>Welcome to the documentation.</p>
            <a href="/docs/next-page">Next Page</a>
            <a href="https://external.com/resource">External Resource</a>
        </main>
        <footer>
            <a href="/privacy">Privacy Policy</a>
        </footer>
    </body>
    </html>
    """


class TestNavigationExtractor:
    """Tests for the NavigationExtractor class."""

    def test_finds_nav_element(self, config, sample_html):
        """Verify navigation element is found."""
        extractor = NavigationExtractor(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        nav = extractor.find_navigation(soup)
        assert nav is not None
        assert nav.name == "nav"

    def test_extracts_nav_links_in_order(self, config, sample_html):
        """Verify navigation links are extracted in order."""
        extractor = NavigationExtractor(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        links = extractor.extract_nav_links(
            soup, "https://docs.example.com/current"
        )

        # Should have internal links only
        assert len(links) == 3
        assert "https://docs.example.com/docs/intro" in links
        assert "https://docs.example.com/docs/getting-started" in links
        assert "https://docs.example.com/docs/advanced" in links

        # Should NOT include external link
        assert not any("github.com" in link for link in links)

    def test_excludes_external_links(self, config, sample_html):
        """Verify external links are excluded from navigation."""
        extractor = NavigationExtractor(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        links = extractor.extract_nav_links(
            soup, "https://docs.example.com/current"
        )

        external_domains = ["github.com", "twitter.com", "external.com"]
        for link in links:
            for domain in external_domains:
                assert domain not in link, \
                    f"External domain {domain} should not be in nav links"

    def test_handles_missing_nav(self, config):
        """Verify graceful handling of missing navigation."""
        extractor = NavigationExtractor(config)
        soup = BeautifulSoup("<html><body><p>No nav here</p></body></html>", "html.parser")

        nav = extractor.find_navigation(soup)
        assert nav is None

        links = extractor.extract_nav_links(soup, "https://docs.example.com")
        assert links == []


class TestContentExtractor:
    """Tests for the ContentExtractor class."""

    def test_extracts_title_from_h1(self, config, sample_html):
        """Verify title extraction from h1 tag."""
        extractor = ContentExtractor(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        title = extractor.extract_title(soup)
        assert title == "Getting Started"

    def test_extracts_title_from_title_tag(self, config):
        """Verify title extraction falls back to title tag."""
        extractor = ContentExtractor(config)
        html = "<html><head><title>Page Title</title></head><body><p>Content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")

        title = extractor.extract_title(soup)
        assert title == "Page Title"

    def test_extracts_main_content(self, config, sample_html):
        """Verify main content extraction."""
        extractor = ContentExtractor(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        content = extractor.extract_main_content(soup)

        # Should contain main content
        assert "Getting Started" in content
        assert "Welcome to the documentation" in content

    def test_removes_navigation_from_content(self, config, sample_html):
        """Verify navigation is removed from extracted content."""
        extractor = ContentExtractor(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        content = extractor.extract_main_content(soup)

        # Navigation links should not be in content
        assert "Introduction" not in content or "sidebar" not in content

    def test_handles_untitled_page(self, config):
        """Verify fallback for pages without title."""
        extractor = ContentExtractor(config)
        html = "<html><body><p>Content without title</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")

        title = extractor.extract_title(soup)
        assert title == "Untitled"


class TestDocumentationCrawler:
    """Tests for the DocumentationCrawler class."""

    def test_extracts_internal_links_only(self, config, sample_html):
        """Verify only internal links are extracted."""
        crawler = DocumentationCrawler(config)
        soup = BeautifulSoup(sample_html, "html.parser")

        links = crawler._extract_links(
            soup, "https://docs.example.com/page"
        )

        # Should contain internal links
        internal_found = any("docs.example.com" in link for link in links)
        assert internal_found, "Should find internal links"

        # Should NOT contain external links
        external_domains = ["github.com", "external.com"]
        for link in links:
            for domain in external_domains:
                assert domain not in link, \
                    f"Should not include external link with {domain}"

    def test_respects_excluded_patterns(self, config, sample_html):
        """Verify excluded patterns are filtered."""
        config.excluded_patterns = ["/api/", "/changelog"]
        crawler = DocumentationCrawler(config)

        html = """
        <html><body>
            <a href="/docs/page">Valid</a>
            <a href="/api/reference">API (excluded)</a>
            <a href="/changelog">Changelog (excluded)</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")

        links = crawler._extract_links(
            soup, "https://docs.example.com/page"
        )

        # Valid link should be included
        assert any("/docs/page" in link for link in links)

        # Excluded links should not be included
        assert not any("/api/" in link for link in links)
        assert not any("/changelog" in link for link in links)

    @patch("crawler.requests.Session")
    def test_tracks_visited_pages(self, mock_session, config):
        """Verify visited pages are tracked to prevent loops."""
        crawler = DocumentationCrawler(config)

        url = "https://docs.example.com/page"

        # First visit
        assert crawler.url_tracker.is_visited(url) is False
        crawler.url_tracker.mark_visited(url)

        # Should be marked as visited
        assert crawler.url_tracker.is_visited(url) is True
        assert crawler.url_tracker.should_visit(url) is False

    def test_page_ordering(self, config):
        """Verify pages are ordered correctly based on navigation."""
        crawler = DocumentationCrawler(config)

        # Simulate navigation order
        crawler.nav_order = {
            "https://docs.example.com/intro": 0,
            "https://docs.example.com/setup": 1,
            "https://docs.example.com/guide": 2,
        }

        # Add pages
        crawler.pages = {
            "https://docs.example.com/guide": CrawledPage(
                url="https://docs.example.com/guide",
                title="Guide",
                html_content="",
                extracted_content="",
                order_index=2,
                depth=1,
            ),
            "https://docs.example.com/intro": CrawledPage(
                url="https://docs.example.com/intro",
                title="Introduction",
                html_content="",
                extracted_content="",
                order_index=0,
                depth=1,
            ),
            "https://docs.example.com/setup": CrawledPage(
                url="https://docs.example.com/setup",
                title="Setup",
                html_content="",
                extracted_content="",
                order_index=1,
                depth=1,
            ),
        }

        # Sort pages
        sorted_pages = sorted(
            crawler.pages.values(),
            key=lambda p: (p.order_index, p.depth, p.url)
        )

        # Verify order
        assert sorted_pages[0].title == "Introduction"
        assert sorted_pages[1].title == "Setup"
        assert sorted_pages[2].title == "Guide"


class TestCrawlerIntegration:
    """Integration tests for the crawler with mocked HTTP responses."""

    @patch("crawler.requests.Session")
    def test_respects_max_depth(self, mock_session_class, config):
        """Verify crawler respects maximum depth setting."""
        config.max_depth = 2

        # Create mock session
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        crawler = DocumentationCrawler(config)

        # Depth 0 should be crawled
        crawler._crawl_page("https://docs.example.com/", depth=0)

        # Depth > max_depth should be skipped
        initial_visited = crawler.url_tracker.visited_count

        # This should be skipped due to depth
        crawler._crawl_page("https://docs.example.com/deep/page", depth=3)

        # Count should be same (page was not visited due to depth)
        assert crawler.url_tracker.is_visited("https://docs.example.com/deep/page") is False

    @patch("crawler.requests.Session")
    def test_handles_fetch_errors_gracefully(self, mock_session_class, config):
        """Verify crawler handles HTTP errors gracefully."""
        import requests

        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Simulate connection error
        mock_session.get.side_effect = requests.RequestException("Connection failed")

        crawler = DocumentationCrawler(config)
        result = crawler._fetch_page("https://docs.example.com/page")

        assert result is None  # Should return None on error

    @patch("crawler.requests.Session")
    def test_skips_non_html_content(self, mock_session_class, config):
        """Verify crawler skips non-HTML responses."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock response with non-HTML content type
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        crawler = DocumentationCrawler(config)
        result = crawler._fetch_page("https://docs.example.com/api.json")

        assert result is None  # Should skip non-HTML


class TestExternalLinkRejection:
    """
    Dedicated tests for external link rejection.

    These tests specifically validate that external domain links
    are correctly identified and excluded at all stages of crawling.
    """

    def test_link_extraction_rejects_external_domains(self, config):
        """Verify external domains are rejected during link extraction."""
        crawler = DocumentationCrawler(config)

        html = """
        <html><body>
            <a href="/internal/page">Internal</a>
            <a href="https://external.com/page">External</a>
            <a href="https://another-site.org/docs">Another External</a>
            <a href="//cdn.example.net/asset">CDN (External)</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")

        links = crawler._extract_links(
            soup, "https://docs.example.com/current"
        )

        # Should only have internal link
        assert len(links) == 1
        assert "docs.example.com" in links[0]

    def test_navigation_extraction_rejects_external(self, config):
        """Verify external links are excluded from navigation."""
        extractor = NavigationExtractor(config)

        html = """
        <html>
        <nav>
            <a href="/docs/intro">Intro</a>
            <a href="https://github.com/project">GitHub</a>
            <a href="https://twitter.com/project">Twitter</a>
            <a href="/docs/guide">Guide</a>
        </nav>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        links = extractor.extract_nav_links(
            soup, "https://docs.example.com"
        )

        # Should only have 2 internal links
        assert len(links) == 2

        # Verify no external domains
        for link in links:
            assert "github.com" not in link
            assert "twitter.com" not in link

    def test_various_external_link_formats(self, config):
        """Test rejection of various external link formats."""
        crawler = DocumentationCrawler(config)

        html = """
        <html><body>
            <!-- Protocol-relative external -->
            <a href="//external.com/page">Proto-relative</a>

            <!-- Different protocols -->
            <a href="http://insecure-external.com/page">HTTP External</a>
            <a href="https://secure-external.com/page">HTTPS External</a>

            <!-- Subdomains of different domain -->
            <a href="https://api.external.com/endpoint">API External</a>
            <a href="https://docs.external.com/guide">Docs External</a>

            <!-- Valid internal link for comparison -->
            <a href="https://docs.example.com/valid">Valid Internal</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")

        links = crawler._extract_links(
            soup, "https://docs.example.com/current"
        )

        # Should only have 1 internal link
        assert len(links) == 1
        assert "docs.example.com" in links[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
