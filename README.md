# Web2PDF - Documentation Crawler

A Python application that crawls documentation websites and converts all pages into a single, merged PDF file for offline reading.

## Features

- **Recursive Crawling**: Automatically discovers and crawls all internal pages starting from a root URL
- **External Link Filtering**: Only follows links within the same domain and path hierarchy
- **Navigation-Aware Ordering**: Maintains logical reading order by following sidebar/navigation structure
- **JavaScript Support**: Optional Playwright integration for JavaScript-rendered sites (React, Vue, MkDocs, etc.)
- **PDF Generation**: Converts HTML to PDF with proper styling, code formatting, and table of contents
- **Configurable**: Adjustable depth limits, request delays, exclusion patterns, and more

## Installation

### Prerequisites

- Python 3.8+

### Setup

```bash
# Clone the repository
git clone https://github.com/thomasckr/web2pdf-claude.git
cd web2pdf-claude

# Install dependencies
pip install -r requirements.txt

# (Optional) For JavaScript-rendered sites, install Playwright
pip install playwright
playwright install chromium
```

## Usage

### Basic Usage

```bash
# Crawl a documentation site
python main.py --url https://docs.example.com/guide/ --output documentation.pdf
```

### Command Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--url` | `-u` | Root URL of the documentation site | Required |
| `--output` | `-o` | Output PDF filename | `documentation.pdf` |
| `--max-depth` | `-d` | Maximum crawl depth | `10` |
| `--delay` | | Delay between requests (seconds) | `0.5` |
| `--timeout` | | Request timeout (seconds) | `30` |
| `--javascript` | `-js` | Use Playwright for JS-rendered pages | `False` |
| `--no-toc` | | Disable table of contents | `False` |
| `--exclude` | | URL patterns to exclude | `[]` |
| `--verbose` | `-v` | Enable debug logging | `False` |

### Examples

```bash
# Crawl Python tutorial documentation
python main.py --url https://docs.python.org/3/tutorial/ --output python-tutorial.pdf

# Crawl with limited depth
python main.py --url https://docs.example.com/ --output docs.pdf --max-depth 3

# Crawl JavaScript-rendered site (requires Playwright)
python main.py --url https://react.dev/learn --output react-docs.pdf --javascript

# Exclude certain paths
python main.py --url https://docs.example.com/ --output docs.pdf --exclude /api/ /changelog

# Verbose output with custom delay
python main.py --url https://docs.example.com/ --output docs.pdf --verbose --delay 1.0
```

## Project Structure

```
web2pdf-claude/
├── main.py           # CLI entry point
├── config.py         # Configuration settings
├── url_utils.py      # URL parsing, normalization, filtering
├── crawler.py        # Web crawler (standard + Playwright modes)
├── pdf_converter.py  # HTML-to-PDF conversion and merging
├── requirements.txt  # Python dependencies
└── tests/            # Unit tests
    ├── test_url_utils.py
    └── test_crawler.py
```

## How It Works

1. **Crawling**: Starting from the root URL, the crawler discovers all internal links while respecting the domain and path boundaries
2. **Ordering**: Links are extracted from navigation elements (sidebars, menus) to maintain logical reading order
3. **Content Extraction**: Main content is extracted from each page, removing navigation, headers, and footers
4. **PDF Conversion**: Each page is converted to PDF using xhtml2pdf with consistent styling
5. **Merging**: All PDFs are merged into a single document with an optional table of contents

## Configuration

The `config.py` file contains default settings that can be customized:

- `nav_selectors`: CSS selectors for finding navigation elements
- `content_selectors`: CSS selectors for extracting main content
- `excluded_patterns`: URL patterns to skip during crawling
- `pdf_page_size`: Output PDF page size (default: A4)
- `pdf_margin`: Page margins (default: 2cm)

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=.
```

## Limitations

- **CAPTCHA/Bot Protection**: Sites with Cloudflare or similar protection cannot be crawled automatically
- **Login-Required Content**: Does not support authenticated pages
- **Dynamic Content**: Some heavily JavaScript-dependent sites may require the `--javascript` flag
- **Large Sites**: Very large documentation sites may take significant time to crawl

## Dependencies

- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `xhtml2pdf` - HTML to PDF conversion
- `pypdf` - PDF merging
- `playwright` (optional) - JavaScript rendering

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
