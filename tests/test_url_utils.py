"""
Unit tests for the URL utilities module.

Tests cover:
- URL normalization
- Domain extraction and comparison
- URL resolution (relative/absolute)
- URL validation and filtering
- URL tracker state management
"""

import pytest
from url_utils import (
    normalize_url,
    extract_domain,
    is_same_domain,
    resolve_url,
    is_valid_doc_url,
    get_url_path,
    get_url_depth,
    create_url_key,
    URLTracker,
)


class TestNormalizeUrl:
    """Tests for the normalize_url function."""

    def test_removes_fragment(self):
        """Verify that URL fragments are removed."""
        url = "https://docs.example.com/page#section"
        assert normalize_url(url) == "https://docs.example.com/page"

    def test_removes_trailing_slash(self):
        """Verify that trailing slashes are removed."""
        url = "https://docs.example.com/page/"
        assert normalize_url(url) == "https://docs.example.com/page"

    def test_preserves_root_slash(self):
        """Verify that root path keeps its slash."""
        url = "https://docs.example.com/"
        assert normalize_url(url) == "https://docs.example.com/"

    def test_handles_no_path(self):
        """Verify URLs without path are handled."""
        url = "https://docs.example.com"
        assert normalize_url(url) == "https://docs.example.com/"

    def test_preserves_query_string(self):
        """Verify that query strings are preserved."""
        url = "https://docs.example.com/search?q=test"
        assert normalize_url(url) == "https://docs.example.com/search?q=test"

    def test_removes_fragment_with_query(self):
        """Verify fragments are removed while preserving query strings."""
        url = "https://docs.example.com/page?q=test#section"
        assert normalize_url(url) == "https://docs.example.com/page?q=test"


class TestExtractDomain:
    """Tests for the extract_domain function."""

    def test_extracts_simple_domain(self):
        """Verify simple domain extraction."""
        assert extract_domain("https://docs.example.com/page") == "docs.example.com"

    def test_extracts_www_domain(self):
        """Verify www subdomain extraction."""
        assert extract_domain("https://www.example.com/page") == "www.example.com"

    def test_handles_port_number(self):
        """Verify domains with ports are handled."""
        assert extract_domain("https://localhost:8000/page") == "localhost:8000"

    def test_lowercase_domain(self):
        """Verify domain is returned in lowercase."""
        assert extract_domain("https://DOCS.Example.COM/page") == "docs.example.com"


class TestIsSameDomain:
    """Tests for the is_same_domain function."""

    def test_same_domain_returns_true(self):
        """Verify same domain comparison returns True."""
        url = "https://docs.example.com/page"
        base = "https://docs.example.com"
        assert is_same_domain(url, base) is True

    def test_different_domain_returns_false(self):
        """Verify different domain comparison returns False."""
        url = "https://external.com/page"
        base = "https://docs.example.com"
        assert is_same_domain(url, base) is False

    def test_handles_www_variation(self):
        """Verify www prefix variations are treated as same domain."""
        url = "https://www.example.com/page"
        base = "https://example.com"
        assert is_same_domain(url, base) is True

    def test_subdomain_is_different(self):
        """Verify subdomains are treated as different domains."""
        url = "https://api.example.com/page"
        base = "https://docs.example.com"
        assert is_same_domain(url, base) is False

    def test_external_link_rejected(self):
        """Verify external links are correctly identified."""
        external_urls = [
            "https://github.com/example",
            "https://twitter.com/example",
            "https://cdn.example.org/asset",
            "http://different-site.com/page",
        ]
        base = "https://docs.example.com"

        for url in external_urls:
            assert is_same_domain(url, base) is False, f"Expected {url} to be external"


class TestResolveUrl:
    """Tests for the resolve_url function."""

    def test_resolves_absolute_url(self):
        """Verify absolute URLs are returned as-is."""
        href = "https://docs.example.com/other"
        current = "https://docs.example.com/page"
        assert resolve_url(href, current) == "https://docs.example.com/other"

    def test_resolves_root_relative_url(self):
        """Verify root-relative URLs are resolved correctly."""
        href = "/docs/page"
        current = "https://docs.example.com/other"
        assert resolve_url(href, current) == "https://docs.example.com/docs/page"

    def test_resolves_relative_url(self):
        """Verify relative URLs are resolved correctly."""
        href = "subpage"
        current = "https://docs.example.com/docs/"
        assert resolve_url(href, current) == "https://docs.example.com/docs/subpage"

    def test_resolves_parent_relative_url(self):
        """Verify parent-relative URLs are resolved correctly."""
        href = "../other"
        current = "https://docs.example.com/docs/page"
        assert resolve_url(href, current) == "https://docs.example.com/other"

    def test_rejects_fragment_only(self):
        """Verify fragment-only hrefs are rejected."""
        assert resolve_url("#section", "https://example.com/page") is None

    def test_rejects_javascript_url(self):
        """Verify javascript: URLs are rejected."""
        assert resolve_url("javascript:void(0)", "https://example.com") is None

    def test_rejects_mailto_url(self):
        """Verify mailto: URLs are rejected."""
        assert resolve_url("mailto:test@example.com", "https://example.com") is None

    def test_rejects_empty_href(self):
        """Verify empty hrefs are rejected."""
        assert resolve_url("", "https://example.com") is None


class TestIsValidDocUrl:
    """Tests for the is_valid_doc_url function."""

    def test_valid_internal_url(self):
        """Verify valid internal URLs are accepted."""
        url = "https://docs.example.com/guide/intro"
        base = "https://docs.example.com"
        excluded = []
        assert is_valid_doc_url(url, base, excluded) is True

    def test_rejects_external_url(self):
        """Verify external URLs are rejected."""
        url = "https://github.com/example"
        base = "https://docs.example.com"
        excluded = []
        assert is_valid_doc_url(url, base, excluded) is False

    def test_rejects_excluded_pattern(self):
        """Verify URLs matching excluded patterns are rejected."""
        url = "https://docs.example.com/api/reference"
        base = "https://docs.example.com"
        excluded = ["/api/"]
        assert is_valid_doc_url(url, base, excluded) is False

    def test_rejects_non_html_extensions(self):
        """Verify non-HTML file extensions are rejected."""
        base = "https://docs.example.com"
        excluded = []

        non_html_urls = [
            "https://docs.example.com/image.png",
            "https://docs.example.com/style.css",
            "https://docs.example.com/script.js",
            "https://docs.example.com/data.json",
            "https://docs.example.com/archive.zip",
            "https://docs.example.com/document.pdf",
        ]

        for url in non_html_urls:
            assert is_valid_doc_url(url, base, excluded) is False, \
                f"Expected {url} to be rejected"

    def test_accepts_html_extensions(self):
        """Verify HTML file extensions are accepted."""
        base = "https://docs.example.com"
        excluded = []

        html_urls = [
            "https://docs.example.com/page.html",
            "https://docs.example.com/page.htm",
            "https://docs.example.com/page/",
            "https://docs.example.com/page",
        ]

        for url in html_urls:
            assert is_valid_doc_url(url, base, excluded) is True, \
                f"Expected {url} to be accepted"

    def test_case_insensitive_exclusion(self):
        """Verify exclusion patterns are case-insensitive."""
        url = "https://docs.example.com/API/reference"
        base = "https://docs.example.com"
        excluded = ["/api/"]
        assert is_valid_doc_url(url, base, excluded) is False


class TestGetUrlPath:
    """Tests for the get_url_path function."""

    def test_extracts_path(self):
        """Verify path extraction."""
        assert get_url_path("https://example.com/docs/page") == "/docs/page"

    def test_handles_root_path(self):
        """Verify root path extraction."""
        assert get_url_path("https://example.com/") == "/"

    def test_handles_no_path(self):
        """Verify handling of URLs without explicit path."""
        assert get_url_path("https://example.com") == ""


class TestGetUrlDepth:
    """Tests for the get_url_depth function."""

    def test_same_path_is_zero_depth(self):
        """Verify same path returns depth 0."""
        url = "https://docs.example.com/docs"
        base = "https://docs.example.com/docs"
        assert get_url_depth(url, base) == 0

    def test_one_level_deeper(self):
        """Verify one level deeper returns depth 1."""
        url = "https://docs.example.com/docs/page"
        base = "https://docs.example.com/docs"
        assert get_url_depth(url, base) == 1

    def test_multiple_levels_deeper(self):
        """Verify multiple levels deeper returns correct depth."""
        url = "https://docs.example.com/docs/guide/section/page"
        base = "https://docs.example.com/docs"
        assert get_url_depth(url, base) == 3


class TestCreateUrlKey:
    """Tests for the create_url_key function."""

    def test_creates_consistent_key(self):
        """Verify consistent keys for equivalent URLs."""
        url1 = "https://docs.example.com/page/"
        url2 = "https://docs.example.com/page#section"
        url3 = "https://DOCS.EXAMPLE.COM/page"

        key1 = create_url_key(url1)
        key2 = create_url_key(url2)
        key3 = create_url_key(url3)

        assert key1 == key2 == key3


class TestURLTracker:
    """Tests for the URLTracker class."""

    def test_marks_visited(self):
        """Verify URL can be marked as visited."""
        tracker = URLTracker()
        url = "https://docs.example.com/page"

        assert tracker.is_visited(url) is False
        tracker.mark_visited(url)
        assert tracker.is_visited(url) is True

    def test_marks_queued(self):
        """Verify URL can be marked as queued."""
        tracker = URLTracker()
        url = "https://docs.example.com/page"

        assert tracker.is_queued(url) is False
        tracker.mark_queued(url)
        assert tracker.is_queued(url) is True

    def test_should_visit_logic(self):
        """Verify should_visit returns correct values."""
        tracker = URLTracker()
        url = "https://docs.example.com/page"

        # Should visit when not visited or queued
        assert tracker.should_visit(url) is True

        # Should not visit when queued
        tracker.mark_queued(url)
        assert tracker.should_visit(url) is False

        # Should not visit when visited
        tracker2 = URLTracker()
        tracker2.mark_visited(url)
        assert tracker2.should_visit(url) is False

    def test_handles_url_variations(self):
        """Verify tracker handles URL variations correctly."""
        tracker = URLTracker()

        tracker.mark_visited("https://docs.example.com/page/")
        assert tracker.is_visited("https://docs.example.com/page#section") is True
        assert tracker.is_visited("https://DOCS.EXAMPLE.COM/page") is True

    def test_counts(self):
        """Verify count properties work correctly."""
        tracker = URLTracker()

        assert tracker.visited_count == 0
        assert tracker.queued_count == 0

        tracker.mark_visited("https://example.com/page1")
        tracker.mark_visited("https://example.com/page2")
        tracker.mark_queued("https://example.com/page3")

        assert tracker.visited_count == 2
        assert tracker.queued_count == 1


class TestExternalLinkFiltering:
    """
    Integration tests specifically for external link filtering.

    These tests validate the primary requirement that external domain
    links are correctly identified and excluded from crawling.
    """

    def test_comprehensive_external_detection(self):
        """Test that various external link patterns are detected."""
        base_url = "https://docs.myproject.io"
        excluded = []

        internal_urls = [
            "https://docs.myproject.io/guide",
            "https://docs.myproject.io/api/reference",
            "https://docs.myproject.io/tutorials/getting-started",
        ]

        external_urls = [
            # Different TLDs
            "https://docs.myproject.com/guide",
            "https://docs.myproject.org/guide",
            # Different domains
            "https://github.com/myproject/repo",
            "https://stackoverflow.com/questions/123",
            "https://npmjs.com/package/myproject",
            "https://cdn.external.com/asset.js",
            # CDN and third-party services
            "https://fonts.googleapis.com/css",
            "https://analytics.google.com/track",
            # Social media
            "https://twitter.com/myproject",
            "https://discord.gg/invite",
        ]

        # Verify internal URLs are accepted
        for url in internal_urls:
            assert is_valid_doc_url(url, base_url, excluded) is True, \
                f"Expected internal URL {url} to be accepted"

        # Verify external URLs are rejected
        for url in external_urls:
            assert is_valid_doc_url(url, base_url, excluded) is False, \
                f"Expected external URL {url} to be rejected"

    def test_protocol_variations(self):
        """Test that protocol variations don't affect domain matching."""
        base_url = "https://docs.example.com"

        # HTTP vs HTTPS for same domain should match
        assert is_same_domain("http://docs.example.com/page", base_url) is True
        assert is_same_domain("https://docs.example.com/page", base_url) is True

    def test_path_does_not_affect_domain_matching(self):
        """Verify that path differences don't affect domain matching."""
        base_url = "https://docs.example.com/v2"

        # Same domain but different paths
        assert is_same_domain("https://docs.example.com/v1/page", base_url) is True
        assert is_same_domain("https://docs.example.com/api", base_url) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
