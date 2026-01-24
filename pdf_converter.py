"""
PDF Converter module for the Web-to-PDF Documentation Crawler.

This module handles:
- Converting HTML content to PDF using xhtml2pdf (cross-platform, no external dependencies)
- Merging multiple PDFs into a single document
- Adding page numbers and table of contents
- Styling the output for optimal readability
"""

import io
import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from xhtml2pdf import pisa
from pypdf import PdfWriter, PdfReader

from config import CrawlerConfig
from crawler import CrawledPage

logger = logging.getLogger(__name__)


# Default CSS for PDF styling
DEFAULT_PDF_CSS = """
@page {
    size: A4;
    margin: 2cm;
}

/* Base typography */
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #333;
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
    border-bottom: 2px solid #e0e0e0;
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

/* Code styling */
pre, code {
    font-family: Courier, monospace;
    font-size: 9pt;
    background-color: #f6f8fa;
}

code {
    padding: 2px 4px;
}

pre {
    padding: 10px;
    border: 1px solid #e0e0e0;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
}

/* Links */
a {
    color: #0366d6;
    text-decoration: none;
}

/* Lists */
ul, ol {
    padding-left: 20px;
    margin: 10px 0;
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

/* Images */
img {
    max-width: 100%;
    height: auto;
}

/* Blockquotes */
blockquote {
    border-left: 3px solid #ddd;
    margin: 10px 0;
    padding: 5px 15px;
    color: #666;
    background-color: #f9f9f9;
}

/* Page break utilities */
.page-break {
    page-break-before: always;
}

/* Section divider */
.section-divider {
    border: none;
    border-top: 1px solid #ccc;
    margin: 20px 0;
}

/* Navigation elements - hide in PDF */
nav, .sidebar, .navigation, .toc, .breadcrumb {
    display: none;
}
"""


@dataclass
class PDFPage:
    """
    Represents a single PDF page generated from HTML content.

    Attributes:
        title: The page title.
        pdf_bytes: The PDF content as bytes.
        page_count: Number of pages in this PDF section.
    """
    title: str
    pdf_bytes: bytes
    page_count: int


class HTMLToPDFConverter:
    """
    Convert HTML content to PDF using xhtml2pdf.

    Handles the conversion of individual pages and provides
    consistent styling across all pages.
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the HTML to PDF converter.

        Args:
            config: The crawler configuration.
        """
        self.config = config

    def convert_page(self, page: CrawledPage, base_url: str) -> Optional[PDFPage]:
        """
        Convert a single crawled page to PDF.

        Args:
            page: The crawled page to convert.
            base_url: The base URL for resolving relative resources.

        Returns:
            A PDFPage object, or None if conversion failed.
        """
        try:
            # Wrap content in a complete HTML document with styling
            html_content = self._wrap_content(page)

            # Create PDF using xhtml2pdf
            pdf_buffer = io.BytesIO()

            # Convert HTML to PDF
            pisa_status = pisa.CreatePDF(
                src=html_content,
                dest=pdf_buffer,
                encoding='utf-8',
            )

            if pisa_status.err:
                logger.warning(f"PDF conversion had errors for {page.url}")

            pdf_buffer.seek(0)
            pdf_content = pdf_buffer.read()

            # Count pages
            try:
                reader = PdfReader(io.BytesIO(pdf_content))
                page_count = len(reader.pages)
            except Exception:
                page_count = 1

            logger.info(f"Converted: {page.title} ({page_count} pages)")

            return PDFPage(
                title=page.title,
                pdf_bytes=pdf_content,
                page_count=page_count,
            )

        except Exception as e:
            logger.error(f"Failed to convert {page.url}: {e}")
            return None

    def _wrap_content(self, page: CrawledPage) -> str:
        """
        Wrap extracted content in a complete HTML document.

        Args:
            page: The crawled page.

        Returns:
            Complete HTML document string.
        """
        # Escape title for HTML
        safe_title = (page.title
                      .replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;"))

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>{safe_title}</title>
            <style>
            {DEFAULT_PDF_CSS}
            </style>
        </head>
        <body>
            <article>
                <h1>{safe_title}</h1>
                {page.extracted_content}
            </article>
        </body>
        </html>
        """


class PDFMerger:
    """
    Merge multiple PDF documents into a single file.

    Handles combining individual page PDFs with optional
    table of contents and page numbering.
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the PDF merger.

        Args:
            config: The crawler configuration.
        """
        self.config = config

    def merge(
        self,
        pdf_pages: List[PDFPage],
        output_path: str,
        add_toc: bool = True,
    ) -> bool:
        """
        Merge multiple PDF pages into a single document.

        Args:
            pdf_pages: List of PDF pages to merge.
            output_path: Path for the output PDF file.
            add_toc: Whether to add a table of contents.

        Returns:
            True if merge was successful, False otherwise.
        """
        if not pdf_pages:
            logger.error("No pages to merge")
            return False

        try:
            writer = PdfWriter()

            # Track page numbers for TOC
            current_page = 1
            toc_entries = []

            # Add each PDF to the merged document
            for pdf_page in pdf_pages:
                try:
                    reader = PdfReader(io.BytesIO(pdf_page.pdf_bytes))

                    # Record TOC entry
                    toc_entries.append({
                        "title": pdf_page.title,
                        "page": current_page,
                    })

                    # Add all pages from this PDF
                    for pdf_pg in reader.pages:
                        writer.add_page(pdf_pg)

                    current_page += pdf_page.page_count
                except Exception as e:
                    logger.warning(f"Failed to add page '{pdf_page.title}': {e}")
                    continue

            # Generate and prepend TOC if requested
            if add_toc and len(toc_entries) > 1:
                toc_pdf = self._generate_toc(toc_entries)
                if toc_pdf:
                    try:
                        toc_reader = PdfReader(io.BytesIO(toc_pdf))
                        # Insert TOC at the beginning
                        for i, toc_pg in enumerate(toc_reader.pages):
                            writer.insert_page(toc_pg, index=i)
                    except Exception as e:
                        logger.warning(f"Failed to add TOC: {e}")

            # Write the merged PDF
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "wb") as f:
                writer.write(f)

            total_pages = len(writer.pages)
            logger.info(
                f"Created merged PDF: {output_path} "
                f"({total_pages} pages, {len(pdf_pages)} sections)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to merge PDFs: {e}")
            return False

    def _generate_toc(self, entries: List[dict]) -> Optional[bytes]:
        """
        Generate a table of contents PDF page.

        Args:
            entries: List of TOC entries with title and page number.

        Returns:
            PDF bytes for the TOC page, or None if generation failed.
        """
        try:
            # Build TOC HTML
            toc_items = []
            for entry in entries:
                # Escape title for HTML
                safe_title = (entry["title"]
                              .replace("&", "&amp;")
                              .replace("<", "&lt;")
                              .replace(">", "&gt;"))
                toc_items.append(
                    f'<tr>'
                    f'<td style="border:none; padding: 5px 0;">{safe_title}</td>'
                    f'<td style="border:none; padding: 5px 0; text-align:right; width:50px;">{entry["page"]}</td>'
                    f'</tr>'
                )

            toc_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Table of Contents</title>
                <style>
                    @page {{
                        size: A4;
                        margin: 2cm;
                    }}
                    body {{
                        font-family: Helvetica, Arial, sans-serif;
                        font-size: 10pt;
                        line-height: 1.6;
                    }}
                    h1 {{
                        font-size: 20pt;
                        border-bottom: 2px solid #333;
                        padding-bottom: 10px;
                        margin-bottom: 20px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                    }}
                    tr {{
                        border-bottom: 1px dotted #ccc;
                    }}
                </style>
            </head>
            <body>
                <h1>Table of Contents</h1>
                <table>
                    {''.join(toc_items)}
                </table>
            </body>
            </html>
            """

            pdf_buffer = io.BytesIO()
            pisa.CreatePDF(src=toc_html, dest=pdf_buffer, encoding='utf-8')
            pdf_buffer.seek(0)
            return pdf_buffer.read()

        except Exception as e:
            logger.warning(f"Failed to generate TOC: {e}")
            return None


class DocumentationPDFGenerator:
    """
    High-level class that orchestrates the entire PDF generation process.

    Combines crawling, conversion, and merging into a simple interface.
    """

    def __init__(self, config: CrawlerConfig):
        """
        Initialize the PDF generator.

        Args:
            config: The crawler configuration.
        """
        self.config = config
        self.converter = HTMLToPDFConverter(config)
        self.merger = PDFMerger(config)

    def generate(
        self,
        pages: List[CrawledPage],
        output_path: Optional[str] = None,
        add_toc: bool = True,
    ) -> bool:
        """
        Generate a merged PDF from crawled pages.

        Args:
            pages: List of crawled pages to convert.
            output_path: Output file path (uses config default if not provided).
            add_toc: Whether to add a table of contents.

        Returns:
            True if generation was successful, False otherwise.
        """
        output_path = output_path or self.config.output_filename

        logger.info(f"Converting {len(pages)} pages to PDF...")

        # Convert each page to PDF
        pdf_pages = []
        for page in pages:
            pdf_page = self.converter.convert_page(page, self.config.base_url)
            if pdf_page:
                pdf_pages.append(pdf_page)

        if not pdf_pages:
            logger.error("No pages were successfully converted")
            return False

        # Merge all PDFs
        return self.merger.merge(pdf_pages, output_path, add_toc=add_toc)
