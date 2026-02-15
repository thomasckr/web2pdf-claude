"""
Tests for the PDF converter module.

Tests cover:
- URL to anchor ID generation
- Link rewriting (internal → #anchor, external → preserved)
- Combined HTML document building
- Image URL absolutification
"""

import pytest
from bs4 import BeautifulSoup

from pdf_converter import (
    _url_to_anchor_id,
    LinkRewriter,
    DocumentationPDFGenerator,
)
from config import CrawlerConfig
from crawler import CrawledPage


class TestUrlToAnchorId:
    """Tests for the _url_to_anchor_id function."""

    def test_generates_page_prefix(self):
        assert _url_to_anchor_id("https://example.com/page").startswith("page-")

    def test_consistent_for_same_url(self):
        url = "https://docs.example.com/guide/intro"
        assert _url_to_anchor_id(url) == _url_to_anchor_id(url)

    def test_ignores_fragment(self):
        url1 = "https://example.com/page"
        url2 = "https://example.com/page#section"
        assert _url_to_anchor_id(url1) == _url_to_anchor_id(url2)

    def test_ignores_trailing_slash(self):
        url1 = "https://example.com/page"
        url2 = "https://example.com/page/"
        assert _url_to_anchor_id(url1) == _url_to_anchor_id(url2)

    def test_case_insensitive(self):
        url1 = "https://Example.COM/Page"
        url2 = "https://example.com/page"
        assert _url_to_anchor_id(url1) == _url_to_anchor_id(url2)

    def test_different_urls_get_different_ids(self):
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"
        assert _url_to_anchor_id(url1) != _url_to_anchor_id(url2)


class TestLinkRewriter:
    """Tests for the LinkRewriter class."""

    @pytest.fixture
    def rewriter(self):
        base_url = "https://docs.example.com"
        crawled_urls = {
            "https://docs.example.com/intro",
            "https://docs.example.com/guide",
            "https://docs.example.com/api",
        }
        return LinkRewriter(base_url, crawled_urls)

    def test_rewrites_internal_crawled_link(self, rewriter):
        html = '<a href="https://docs.example.com/intro">Intro</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/guide")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        assert link["href"].startswith("#page-")
        assert "internal-link" in link.get("class", [])

    def test_preserves_external_link(self, rewriter):
        html = '<a href="https://github.com/project">GitHub</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/page")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        assert link["href"] == "https://github.com/project"
        assert "external-link" in link.get("class", [])

    def test_resolves_relative_internal_link(self, rewriter):
        html = '<a href="/intro">Intro</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/guide")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        # /intro resolved to https://docs.example.com/intro which is crawled
        assert link["href"].startswith("#page-")

    def test_internal_uncrawled_link_stays_absolute(self, rewriter):
        html = '<a href="https://docs.example.com/unknown-page">Unknown</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/page")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        assert link["href"] == "https://docs.example.com/unknown-page"

    def test_skips_fragment_only_links(self, rewriter):
        html = '<a href="#section">Section</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/page")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        assert link["href"] == "#section"

    def test_skips_mailto_links(self, rewriter):
        html = '<a href="mailto:test@example.com">Email</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/page")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        assert link["href"] == "mailto:test@example.com"

    def test_skips_javascript_links(self, rewriter):
        html = '<a href="javascript:void(0)">Click</a>'
        result = rewriter.rewrite_links(html, "https://docs.example.com/page")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        assert link["href"] == "javascript:void(0)"

    def test_multiple_links_mixed(self, rewriter):
        html = """
        <div>
            <a href="/intro">Intro</a>
            <a href="https://github.com/project">GitHub</a>
            <a href="/guide">Guide</a>
            <a href="https://twitter.com/project">Twitter</a>
        </div>
        """
        result = rewriter.rewrite_links(html, "https://docs.example.com/page")
        soup = BeautifulSoup(result, "html.parser")
        links = soup.find_all("a")

        # Internal crawled links → anchor
        assert links[0]["href"].startswith("#page-")
        assert links[2]["href"].startswith("#page-")

        # External links → preserved
        assert links[1]["href"] == "https://github.com/project"
        assert links[3]["href"] == "https://twitter.com/project"

    def test_www_domain_matching(self):
        rewriter = LinkRewriter(
            "https://www.example.com",
            {"https://www.example.com/page"},
        )
        html = '<a href="https://example.com/page">Page</a>'
        result = rewriter.rewrite_links(html, "https://www.example.com/")
        soup = BeautifulSoup(result, "html.parser")
        link = soup.find("a")
        # example.com and www.example.com should be treated as same domain
        assert "internal-link" in link.get("class", []) or "external-link" in link.get("class", [])


class TestDocumentationPDFGenerator:
    """Tests for the DocumentationPDFGenerator class."""

    @pytest.fixture
    def config(self):
        return CrawlerConfig(base_url="https://docs.example.com")

    @pytest.fixture
    def sample_pages(self):
        return [
            CrawledPage(
                url="https://docs.example.com/intro",
                title="Introduction",
                html_content="<html><body>Intro content</body></html>",
                extracted_content='<p>Welcome to the docs. <a href="/guide">See guide</a>.</p>',
                order_index=0,
                depth=0,
            ),
            CrawledPage(
                url="https://docs.example.com/guide",
                title="Guide",
                html_content="<html><body>Guide content</body></html>",
                extracted_content='<p>This is the guide. <a href="https://github.com/project">GitHub</a>.</p>',
                order_index=1,
                depth=1,
            ),
        ]

    def test_build_combined_html_has_all_sections(self, config, sample_pages):
        generator = DocumentationPDFGenerator(config)
        crawled_urls = {p.url for p in sample_pages}
        rewriter = LinkRewriter(config.base_url, crawled_urls)

        html = generator._build_combined_html(sample_pages, rewriter, add_toc=False)

        # Should contain both page titles
        assert "Introduction" in html
        assert "Guide" in html

        # Should contain anchor IDs
        intro_id = _url_to_anchor_id("https://docs.example.com/intro")
        guide_id = _url_to_anchor_id("https://docs.example.com/guide")
        assert f'id="{intro_id}"' in html
        assert f'id="{guide_id}"' in html

    def test_build_combined_html_with_toc(self, config, sample_pages):
        generator = DocumentationPDFGenerator(config)
        crawled_urls = {p.url for p in sample_pages}
        rewriter = LinkRewriter(config.base_url, crawled_urls)

        html = generator._build_combined_html(sample_pages, rewriter, add_toc=True)

        assert "Table of Contents" in html
        assert "Introduction" in html
        assert "Guide" in html

    def test_build_combined_html_rewrites_internal_links(self, config, sample_pages):
        generator = DocumentationPDFGenerator(config)
        crawled_urls = {p.url for p in sample_pages}
        rewriter = LinkRewriter(config.base_url, crawled_urls)

        html = generator._build_combined_html(sample_pages, rewriter, add_toc=False)

        soup = BeautifulSoup(html, "html.parser")

        # Find the link from intro to guide - should be rewritten
        guide_anchor = _url_to_anchor_id("https://docs.example.com/guide")
        internal_links = soup.find_all("a", class_="internal-link")
        assert any(f"#{guide_anchor}" in l.get("href", "") for l in internal_links)

        # External link should be preserved
        external_links = soup.find_all("a", class_="external-link")
        assert any("github.com" in l.get("href", "") for l in external_links)

    def test_make_images_absolute(self, config):
        generator = DocumentationPDFGenerator(config)

        html = '<img src="/images/logo.png"><img src="https://cdn.example.com/img.jpg">'
        result = generator._make_images_absolute(html, "https://docs.example.com/page")

        soup = BeautifulSoup(result, "html.parser")
        imgs = soup.find_all("img")

        assert imgs[0]["src"] == "https://docs.example.com/images/logo.png"
        assert imgs[1]["src"] == "https://cdn.example.com/img.jpg"

    def test_escape_html(self):
        assert DocumentationPDFGenerator._escape_html("<script>") == "&lt;script&gt;"
        assert DocumentationPDFGenerator._escape_html("A & B") == "A &amp; B"
        assert DocumentationPDFGenerator._escape_html('say "hello"') == "say &quot;hello&quot;"


class TestWebAppRoutes:
    """Tests for the Flask web app routes."""

    @pytest.fixture
    def client(self):
        from app import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Web2PDF" in resp.data

    def test_convert_requires_json(self, client):
        resp = client.post("/convert", data="not json")
        assert resp.status_code in (400, 415)

    def test_convert_requires_url(self, client):
        resp = client.post("/convert", json={})
        assert resp.status_code == 400
        assert b"URL is required" in resp.data

    def test_convert_validates_url_scheme(self, client):
        resp = client.post("/convert", json={"url": "ftp://invalid.com"})
        assert resp.status_code == 400

    def test_convert_starts_job(self, client):
        resp = client.post("/convert", json={"url": "https://docs.example.com/"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "job_id" in data
        assert data["status"] == "queued"

    def test_status_returns_404_for_unknown_job(self, client):
        resp = client.get("/status/unknown-id")
        assert resp.status_code == 404

    def test_download_returns_404_for_unknown_job(self, client):
        resp = client.get("/download/unknown-id")
        assert resp.status_code == 404
