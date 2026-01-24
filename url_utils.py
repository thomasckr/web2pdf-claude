"""
URL utilities module for the Web-to-PDF Documentation Crawler.

This module provides functions for URL parsing, normalization, validation,
and filtering to ensure only internal documentation links are followed.
"""

from urllib.parse import urlparse, urljoin, urldefrag
from typing import Optional, Set, List
import re


def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing fragments and trailing slashes.

    This ensures that URLs pointing to the same page are treated as identical,
    preventing duplicate visits (e.g., /docs/page and /docs/page#section).

    Args:
        url: The URL to normalize.

    Returns:
        The normalized URL without fragment and with consistent trailing slash.
    """
    # Remove URL fragment (the part after #)
    url_without_fragment, _ = urldefrag(url)

    # Parse the URL
    parsed = urlparse(url_without_fragment)

    # Reconstruct without trailing slash on path (unless it's just "/")
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path

    # Handle empty path
    if not path:
        path = "/"

    # Reconstruct the URL
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"

    # Add query string if present
    if parsed.query:
        normalized += f"?{parsed.query}"

    return normalized


def extract_domain(url: str) -> str:
    """
    Extract the domain (netloc) from a URL.

    Args:
        url: The URL to parse.

    Returns:
        The domain portion of the URL (e.g., 'docs.example.com').
    """
    parsed = urlparse(url)
    return parsed.netloc.lower()


def is_same_domain(url: str, base_url: str) -> bool:
    """
    Check if a URL belongs to the same domain as the base URL.

    This is the primary filter for excluding external links.

    Args:
        url: The URL to check.
        base_url: The base/root URL to compare against.

    Returns:
        True if both URLs share the same domain, False otherwise.
    """
    url_domain = extract_domain(url)
    base_domain = extract_domain(base_url)

    # Handle www prefix variations
    url_domain = url_domain.replace("www.", "")
    base_domain = base_domain.replace("www.", "")

    return url_domain == base_domain


def resolve_url(href: str, current_page_url: str) -> Optional[str]:
    """
    Resolve a relative or absolute URL against the current page URL.

    Handles various URL formats:
    - Absolute URLs (https://example.com/page)
    - Protocol-relative URLs (//example.com/page)
    - Root-relative URLs (/docs/page)
    - Relative URLs (../page, ./page, page)

    Args:
        href: The href attribute value from an anchor tag.
        current_page_url: The URL of the page containing the link.

    Returns:
        The resolved absolute URL, or None if the href is invalid.
    """
    # Skip empty or invalid hrefs
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None

    # Use urljoin to handle all URL resolution cases
    resolved = urljoin(current_page_url, href)

    # Ensure we only return http/https URLs
    parsed = urlparse(resolved)
    if parsed.scheme not in ("http", "https"):
        return None

    return resolved


def get_base_directory(url: str) -> str:
    """
    Get the directory portion of a URL path.

    For /docs/guide/page.html returns /docs/guide
    For /docs/guide/ returns /docs/guide
    For /docs/guide returns /docs/guide

    Args:
        url: The URL to extract directory from.

    Returns:
        The directory path.
    """
    path = urlparse(url).path.rstrip("/")

    # If path ends with a file extension, get the parent directory
    if "." in path.split("/")[-1]:
        # It's a file, get parent directory
        return "/".join(path.split("/")[:-1]) or "/"

    return path or "/"


def is_within_base_path(url: str, base_url: str) -> bool:
    """
    Check if a URL is within the base URL's path hierarchy.

    This ensures we don't crawl parent directories or sibling paths.
    Uses the directory of the base URL if it points to a file.

    Args:
        url: The URL to check.
        base_url: The base URL to compare against.

    Returns:
        True if URL is within or at the same level as base URL path.
    """
    base_dir = get_base_directory(base_url)
    url_path = urlparse(url).path.rstrip("/")

    # URL must start with the base directory
    # e.g., base=/docs/guide/, url=/docs/guide/page -> True
    # e.g., base=/docs/guide/intro.html, url=/docs/guide/page.html -> True
    # e.g., base=/docs/guide, url=/docs -> False
    return url_path.startswith(base_dir) or url_path == base_dir


def is_valid_doc_url(url: str, base_url: str, excluded_patterns: List[str]) -> bool:
    """
    Determine if a URL should be included in the documentation crawl.

    Applies multiple validation rules:
    1. Must be same domain as base URL
    2. Must be within the base URL's path hierarchy
    3. Must not match any excluded patterns
    4. Must be a valid HTTP/HTTPS URL

    Args:
        url: The URL to validate.
        base_url: The root documentation URL.
        excluded_patterns: List of URL patterns to exclude.

    Returns:
        True if the URL should be crawled, False otherwise.
    """
    # Must be same domain
    if not is_same_domain(url, base_url):
        return False

    # Must be within base URL path (don't crawl parent directories)
    if not is_within_base_path(url, base_url):
        return False

    # Parse URL for further checks
    parsed = urlparse(url)

    # Skip non-HTTP(S) URLs
    if parsed.scheme not in ("http", "https"):
        return False

    # Check against excluded patterns
    url_lower = url.lower()
    for pattern in excluded_patterns:
        if pattern.lower() in url_lower:
            return False

    # Check for common non-HTML file extensions to skip
    non_html_extensions = (
        ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
        ".css", ".js", ".json", ".xml", ".ico", ".woff", ".woff2",
        ".ttf", ".eot", ".mp4", ".mp3", ".wav", ".zip", ".tar",
        ".gz", ".rar", ".7z", ".exe", ".dmg", ".pkg", ".deb", ".rpm",
    )
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in non_html_extensions):
        return False

    return True


def get_url_path(url: str) -> str:
    """
    Extract the path component from a URL.

    Args:
        url: The URL to parse.

    Returns:
        The path portion of the URL.
    """
    return urlparse(url).path


def get_url_depth(url: str, base_url: str) -> int:
    """
    Calculate the depth of a URL relative to the base URL.

    This helps prioritize pages closer to the root and can be used
    to limit crawl depth to prevent infinite recursion.

    Args:
        url: The URL to measure.
        base_url: The root URL for comparison.

    Returns:
        The depth level (0 = same as base, 1 = one level deeper, etc.).
    """
    base_path = get_url_path(base_url).rstrip("/")
    url_path = get_url_path(url).rstrip("/")

    # Remove base path prefix if present
    if url_path.startswith(base_path):
        relative_path = url_path[len(base_path):]
    else:
        relative_path = url_path

    # Count path segments
    segments = [s for s in relative_path.split("/") if s]
    return len(segments)


def create_url_key(url: str) -> str:
    """
    Create a unique key for a URL for use in sets and dictionaries.

    This normalizes the URL to ensure consistent tracking of visited pages.

    Args:
        url: The URL to create a key for.

    Returns:
        A normalized string key for the URL.
    """
    return normalize_url(url).lower()


class URLTracker:
    """
    Track visited URLs and manage the crawl queue.

    This class prevents infinite loops by tracking which pages have been
    visited and provides methods for managing the crawl state.
    """

    def __init__(self):
        """Initialize the URL tracker with empty sets."""
        self._visited: Set[str] = set()
        self._queued: Set[str] = set()

    def is_visited(self, url: str) -> bool:
        """Check if a URL has already been visited."""
        return create_url_key(url) in self._visited

    def mark_visited(self, url: str) -> None:
        """Mark a URL as visited."""
        self._visited.add(create_url_key(url))

    def is_queued(self, url: str) -> bool:
        """Check if a URL is already in the queue."""
        return create_url_key(url) in self._queued

    def mark_queued(self, url: str) -> None:
        """Mark a URL as queued for crawling."""
        self._queued.add(create_url_key(url))

    def should_visit(self, url: str) -> bool:
        """Check if a URL should be added to the crawl queue."""
        key = create_url_key(url)
        return key not in self._visited and key not in self._queued

    @property
    def visited_count(self) -> int:
        """Return the number of visited URLs."""
        return len(self._visited)

    @property
    def queued_count(self) -> int:
        """Return the number of queued URLs."""
        return len(self._queued)
