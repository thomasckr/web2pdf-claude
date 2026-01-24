#!/usr/bin/env python3
"""
Web-to-PDF Documentation Crawler

A Python application that crawls documentation websites and converts
all pages into a single, merged PDF file for offline reading.

Usage:
    python main.py                           # Uses default config
    python main.py --url https://docs.example.com
    python main.py --url https://docs.example.com --output docs.pdf
    python main.py --url https://docs.example.com --max-depth 5

Example:
    python main.py --url https://docs.python.org/3/tutorial/ --output python-tutorial.pdf
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from config import CrawlerConfig
from crawler import create_crawler
from pdf_converter import DocumentationPDFGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Crawl documentation websites and convert to PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://docs.example.com
  %(prog)s --url https://docs.example.com --output documentation.pdf
  %(prog)s --url https://docs.example.com --max-depth 5 --delay 1.0
        """,
    )

    parser.add_argument(
        "--url", "-u",
        type=str,
        help="Root URL of the documentation site to crawl",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default="documentation.pdf",
        help="Output PDF filename (default: documentation.pdf)",
    )

    parser.add_argument(
        "--max-depth", "-d",
        type=int,
        default=10,
        help="Maximum crawl depth (default: 10)",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )

    parser.add_argument(
        "--no-toc",
        action="store_true",
        help="Disable table of contents generation",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    parser.add_argument(
        "--exclude",
        type=str,
        nargs="+",
        default=[],
        help="URL patterns to exclude (e.g., /api/ /changelog)",
    )

    parser.add_argument(
        "--javascript", "-js",
        action="store_true",
        help="Use Playwright for JavaScript-rendered pages (requires: pip install playwright && playwright install chromium)",
    )

    return parser.parse_args()


def create_config_from_args(args: argparse.Namespace) -> CrawlerConfig:
    """
    Create a CrawlerConfig from command-line arguments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Configured CrawlerConfig instance.
    """
    config = CrawlerConfig()

    if args.url:
        config.base_url = args.url

    config.output_filename = args.output
    config.max_depth = args.max_depth
    config.request_delay = args.delay
    config.timeout = args.timeout

    # Add any additional exclusion patterns
    if args.exclude:
        config.excluded_patterns.extend(args.exclude)

    return config


def validate_config(config: CrawlerConfig) -> bool:
    """
    Validate the crawler configuration.

    Args:
        config: The configuration to validate.

    Returns:
        True if configuration is valid, False otherwise.
    """
    # Check URL format
    if not config.base_url.startswith(("http://", "https://")):
        logger.error("URL must start with http:// or https://")
        return False

    # Check output path
    output_path = Path(config.output_filename)
    if output_path.suffix.lower() != ".pdf":
        logger.warning("Output file does not have .pdf extension")

    # Check parent directory exists or can be created
    if output_path.parent.name and not output_path.parent.exists():
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Cannot create output directory: {e}")
            return False

    return True


def run_crawler(config: CrawlerConfig, add_toc: bool = True, use_javascript: bool = False) -> bool:
    """
    Run the documentation crawler and PDF generator.

    Args:
        config: The crawler configuration.
        add_toc: Whether to add a table of contents.
        use_javascript: Whether to use Playwright for JS-rendered pages.

    Returns:
        True if successful, False otherwise.
    """
    logger.info("=" * 60)
    logger.info("Web-to-PDF Documentation Crawler")
    logger.info("=" * 60)
    logger.info(f"Base URL: {config.base_url}")
    logger.info(f"Output: {config.output_filename}")
    logger.info(f"Max Depth: {config.max_depth}")
    logger.info(f"JavaScript Mode: {'Enabled (Playwright)' if use_javascript else 'Disabled'}")
    logger.info("=" * 60)

    # Phase 1: Crawl the documentation
    logger.info("\n[Phase 1] Crawling documentation pages...")
    crawler = create_crawler(config, use_javascript=use_javascript)

    try:
        pages = crawler.crawl()
    except KeyboardInterrupt:
        logger.warning("\nCrawling interrupted by user")
        pages = list(crawler.pages.values())
        if not pages:
            return False
        logger.info(f"Continuing with {len(pages)} pages already crawled...")

    if not pages:
        logger.error("No pages were found to convert")
        return False

    # Display crawl statistics
    stats = crawler.get_stats()
    logger.info("\nCrawl Statistics:")
    logger.info(f"  - Pages crawled: {stats['pages_crawled']}")
    logger.info(f"  - Max depth reached: {stats['max_depth_reached']}")

    # Phase 2: Convert to PDF
    logger.info("\n[Phase 2] Converting pages to PDF...")
    generator = DocumentationPDFGenerator(config)

    success = generator.generate(
        pages=pages,
        output_path=config.output_filename,
        add_toc=add_toc,
    )

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("SUCCESS! Documentation PDF created:")
        logger.info(f"  {Path(config.output_filename).absolute()}")
        logger.info("=" * 60)
    else:
        logger.error("\nFailed to generate PDF")

    return success


def main() -> int:
    """
    Main entry point for the application.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    args = parse_arguments()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create configuration
    config = create_config_from_args(args)

    # Validate configuration
    if not validate_config(config):
        return 1

    # Run the crawler
    try:
        success = run_crawler(config, add_toc=not args.no_toc, use_javascript=args.javascript)
        return 0 if success else 1

    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user")
        return 1

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
