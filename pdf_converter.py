"""
PDF Converter module for the Web-to-PDF Documentation Crawler.

This module handles:
- Converting HTML content to PDF using WeasyPrint (preserves hyperlinks)
- Building a single combined HTML document from all crawled pages
- Rewriting internal links to PDF-internal anchors (self-contained document)
- Keeping external links as clickable hyperlinks in the PDF
- Adding table of contents with PDF bookmarks
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin, urldefrag

from bs4 import BeautifulSoup, Tag
from weasyprint import HTML

from config import CrawlerConfig

logger = logging.getLogger(__name__)


# CSS for the combined PDF document
PDF_CSS = """
@page {
    size: A4;
    margin: 2cm 2cm 2.5cm 2cm;
    @bottom-center {
        content: counter(page);
        font-size: 9pt;
        color: #666;
    }
}

/* Base typography */
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #333;
}

/* Page sections */
.doc-page {
    page-break-before: always;
}

.doc-page:first-child {
    page-break-before: avoid;
}

/* Headings */
h1, h2, h3, h4, h5, h6 {
    color: #1a1a1a;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    page-break-after: avoid;
}

h1 {
    font-size: 20pt;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 16pt;
    border-bottom: 1px solid #e0e0e0;
    padding-bottom: 0.2em;
}

h3 { font-size: 13pt; }
h4 { font-size: 11pt; }
h5, h6 { font-size: 10pt; }

/* Page title header */
.page-title {
    font-size: 20pt;
    color: #1a1a1a;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 0.3em;
    margin-top: 0;
    margin-bottom: 0.8em;
}

/* Source URL annotation */
.page-source-url {
    font-size: 8pt;
    color: #999;
    margin-bottom: 1em;
    word-break: break-all;
}

/* Code styling */
pre, code {
    font-family: "Courier New", Courier, monospace;
    font-size: 9pt;
    background-color: #f6f8fa;
}

code {
    padding: 2px 4px;
    border-radius: 3px;
}

pre {
    padding: 12px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

pre code {
    padding: 0;
    background: none;
}

/* Links */
a {
    color: #2563eb;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Internal PDF links get a subtle indicator */
a.internal-link {
    color: #2563eb;
}

/* External links get a visual indicator */
a.external-link {
    color: #0366d6;
}

a.external-link::after {
    content: " ↗";
    font-size: 7pt;
    vertical-align: super;
}

/* Lists */
ul, ol {
    padding-left: 20px;
    margin: 8px 0;
}

li {
    margin: 3px 0;
}

/* Tables */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    page-break-inside: avoid;
    font-size: 9pt;
}

th, td {
    border: 1px solid #ddd;
    padding: 6px 10px;
    text-align: left;
}

th {
    background-color: #f6f8fa;
    font-weight: bold;
}

tr:nth-child(even) {
    background-color: #fafafa;
}

/* Images */
img {
    max-width: 100%;
    height: auto;
}

/* Blockquotes / admonitions */
blockquote {
    border-left: 4px solid #2563eb;
    margin: 10px 0;
    padding: 8px 16px;
    color: #555;
    background-color: #f8f9fa;
}

/* Horizontal rules */
hr {
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 20px 0;
}

/* TOC styling */
.toc-page {
    page-break-after: always;
}

.toc-page h1 {
    font-size: 24pt;
    border-bottom: 3px solid #2563eb;
    margin-bottom: 1em;
}

.toc-entry {
    display: block;
    padding: 4px 0;
    border-bottom: 1px dotted #ddd;
    text-decoration: none;
    color: #333;
}

.toc-entry:hover {
    color: #2563eb;
}

.toc-entry .toc-title {
    display: inline;
}

/* Navigation elements - hide in PDF */
nav, .sidebar, .navigation, .toc, .breadcrumb,
.edit-link, .page-nav, .edit-this-page, .last-updated {
    display: none !important;
}
"""


def _url_to_anchor_id(url: str) -> str:
    """
    Generate a stable, unique anchor ID from a URL.

    Uses a short hash of the normalized URL to create valid HTML IDs.

    Args:
        url: The URL to create an anchor for.

    Returns:
        A valid HTML anchor ID string like 'page-a1b2c3d4'.
    """
    # Remove fragment
    url_clean, _ = urldefrag(url)
    # Normalize: strip trailing slash, lowercase
    url_clean = url_clean.rstrip("/").lower()
    # Create a short hash
    url_hash = hashlib.md5(url_clean.encode()).hexdigest()[:8]
    return f"page-{url_hash}"


class LinkRewriter:
    """
    Rewrites links in HTML content to create a self-contained PDF.

    Internal links (same doc domain) → #anchor references within the PDF.
    External links → preserved as clickable hyperlinks.
    """

    def __init__(self, base_url: str, crawled_urls: set):
        """
        Initialize the link rewriter.

        Args:
            base_url: The base documentation URL.
            crawled_urls: Set of all URLs that were crawled (normalized).
        """
        self.base_url = base_url
        self.crawled_urls = crawled_urls
        self.base_domain = urlparse(base_url).netloc.lower().replace("www.", "")

        # Build URL → anchor mapping for all crawled pages
        self.url_to_anchor: Dict[str, str] = {}
        for url in crawled_urls:
            self.url_to_anchor[self._normalize_for_lookup(url)] = _url_to_anchor_id(url)

    def _normalize_for_lookup(self, url: str) -> str:
        """Normalize a URL for lookup in the anchor map."""
        url_clean, _ = urldefrag(url)
        return url_clean.rstrip("/").lower()

    def _is_internal(self, url: str) -> bool:
        """Check if a URL belongs to the same documentation domain."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        return domain == self.base_domain

    def rewrite_links(self, html_content: str, page_url: str) -> str:
        """
        Rewrite all links in HTML content.

        Internal links to crawled pages → #anchor-id
        Internal links to uncrawled pages → kept as absolute URLs
        External links → kept as-is with external-link class

        Args:
            html_content: The HTML content to process.
            page_url: The URL of the page (for resolving relative links).

        Returns:
            HTML with rewritten links.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")

            # Skip empty/special hrefs
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                continue

            # Resolve relative URLs to absolute
            resolved = urljoin(page_url, href)

            if self._is_internal(resolved):
                # Check if this internal URL was crawled
                lookup_key = self._normalize_for_lookup(resolved)
                if lookup_key in self.url_to_anchor:
                    # Rewrite to internal PDF anchor
                    anchor["href"] = f"#{self.url_to_anchor[lookup_key]}"
                    anchor["class"] = anchor.get("class", []) + ["internal-link"]
                else:
                    # Internal but not crawled - keep as absolute URL
                    anchor["href"] = resolved
                    anchor["class"] = anchor.get("class", []) + ["external-link"]
            else:
                # External link - keep as absolute URL
                anchor["href"] = resolved
                anchor["class"] = anchor.get("class", []) + ["external-link"]

        return str(soup)


class DocumentationPDFGenerator:
    """
    Generate a self-contained PDF from crawled documentation pages.

    Builds a single HTML document with:
    - Each page as a section with an anchor ID
    - Internal links rewritten to #anchor references
    - External links preserved as clickable hyperlinks
    - Table of contents with links to each section
    - Proper PDF bookmarks via WeasyPrint
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the PDF generator.

        Args:
            config: The crawler configuration.
        """
        self.config = config

    def generate(
        self,
        pages: list,
        output_path: Optional[str] = None,
        add_toc: bool = True,
    ) -> bool:
        """
        Generate a merged PDF from crawled pages.

        Args:
            pages: List of CrawledPage objects to convert.
            output_path: Output file path.
            add_toc: Whether to add a table of contents.

        Returns:
            True if generation was successful, False otherwise.
        """
        output_path = output_path or self.config.output_filename

        if not pages:
            logger.error("No pages to convert")
            return False

        logger.info(f"Generating PDF from {len(pages)} pages...")

        try:
            # Collect all crawled URLs for link rewriting
            crawled_urls = {page.url for page in pages}
            rewriter = LinkRewriter(self.config.base_url, crawled_urls)

            # Build the combined HTML document
            combined_html = self._build_combined_html(pages, rewriter, add_toc)

            # Generate PDF using WeasyPrint
            logger.info("Rendering PDF with WeasyPrint...")
            html_doc = HTML(
                string=combined_html,
                base_url=self.config.base_url,
            )
            html_doc.write_pdf(output_path)

            output_file = Path(output_path)
            size_mb = output_file.stat().st_size / (1024 * 1024)
            logger.info(
                f"PDF generated: {output_path} ({size_mb:.1f} MB, {len(pages)} sections)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}")
            return False

    def _build_combined_html(
        self,
        pages: list,
        rewriter: LinkRewriter,
        add_toc: bool,
    ) -> str:
        """
        Build a single HTML document combining all pages.

        Each page becomes a section with an anchor ID for internal linking.

        Args:
            pages: List of CrawledPage objects.
            rewriter: LinkRewriter instance for rewriting links.
            add_toc: Whether to include a table of contents.

        Returns:
            Complete HTML document string.
        """
        sections = []

        # Build page entries for TOC
        toc_entries = []
        for page in pages:
            anchor_id = _url_to_anchor_id(page.url)
            safe_title = self._escape_html(page.title)
            toc_entries.append((anchor_id, safe_title))

        # Generate TOC section
        if add_toc and len(pages) > 1:
            toc_html = self._build_toc_html(toc_entries)
            sections.append(toc_html)

        # Generate each page section
        for i, page in enumerate(pages):
            anchor_id = _url_to_anchor_id(page.url)
            safe_title = self._escape_html(page.title)

            # Rewrite links in the content
            rewritten_content = rewriter.rewrite_links(
                page.extracted_content, page.url
            )

            # Make images absolute so WeasyPrint can fetch them
            rewritten_content = self._make_images_absolute(
                rewritten_content, page.url
            )

            section = f"""
            <div class="doc-page" id="{anchor_id}">
                <h1 class="page-title">{safe_title}</h1>
                <div class="page-source-url">{self._escape_html(page.url)}</div>
                <div class="page-content">
                    {rewritten_content}
                </div>
            </div>
            """
            sections.append(section)
            logger.info(f"  Processed ({i+1}/{len(pages)}): {page.title}")

        # Combine into final HTML
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Documentation</title>
    <style>
    {PDF_CSS}
    </style>
</head>
<body>
    {chr(10).join(sections)}
</body>
</html>"""

    def _build_toc_html(self, entries: list) -> str:
        """
        Build the table of contents HTML section.

        Args:
            entries: List of (anchor_id, title) tuples.

        Returns:
            HTML string for the TOC section.
        """
        toc_links = []
        for anchor_id, title in entries:
            toc_links.append(
                f'<a class="toc-entry" href="#{anchor_id}">'
                f'<span class="toc-title">{title}</span>'
                f'</a>'
            )

        return f"""
        <div class="toc-page">
            <h1>Table of Contents</h1>
            <div class="toc-list">
                {''.join(toc_links)}
            </div>
        </div>
        """

    def _make_images_absolute(self, html_content: str, page_url: str) -> str:
        """
        Convert relative image URLs to absolute URLs.

        This allows WeasyPrint to fetch and embed images in the PDF.

        Args:
            html_content: HTML content with possibly relative image URLs.
            page_url: The page URL for resolving relative paths.

        Returns:
            HTML with absolute image URLs.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        for img in soup.find_all("img", src=True):
            src = img.get("src", "")
            if src and not src.startswith(("http://", "https://", "data:")):
                img["src"] = urljoin(page_url, src)

        return str(soup)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape special HTML characters in text."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
