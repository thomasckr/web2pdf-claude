"""
Flask web application for converting documentation websites to PDF.

Provides a web interface where users can submit a documentation URL
and receive a self-contained PDF with:
- Internal links rewritten to PDF-internal anchors
- External links preserved as clickable hyperlinks
- Table of contents with navigation
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    Response,
)

from config import CrawlerConfig
from crawler import create_crawler
from pdf_converter import DocumentationPDFGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Directory for generated PDFs
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# In-memory job store
# In production, use Redis or a database instead.
jobs: dict = {}


class ConversionJob:
    """Tracks the state of a URL-to-PDF conversion job."""

    def __init__(self, job_id: str, url: str, config: CrawlerConfig):
        self.job_id = job_id
        self.url = url
        self.config = config
        self.status = "queued"  # queued, crawling, converting, completed, failed
        self.progress_messages: list = []
        self.pages_found = 0
        self.pages_processed = 0
        self.output_path: str | None = None
        self.error: str | None = None
        self.started_at = time.time()
        self.completed_at: float | None = None

    def add_message(self, message: str):
        self.progress_messages.append({
            "time": time.time() - self.started_at,
            "message": message,
        })

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "status": self.status,
            "pages_found": self.pages_found,
            "pages_processed": self.pages_processed,
            "progress_messages": self.progress_messages[-20:],  # Last 20 messages
            "error": self.error,
            "elapsed": round(time.time() - self.started_at, 1),
        }


def run_conversion(job: ConversionJob):
    """Run the crawl and PDF conversion in a background thread."""
    try:
        job.status = "crawling"
        job.add_message(f"Starting crawl of {job.url}")

        # Create crawler
        config = job.config
        use_js = False

        # Try to detect if we need JavaScript rendering
        # (for now, always use standard crawler; can be made configurable)
        crawler = create_crawler(config, use_javascript=use_js)

        # Install a logging handler to capture progress
        class JobLogHandler(logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                job.add_message(msg)
                # Track page count from crawler log messages
                if "Crawling" in msg:
                    job.pages_found = len(crawler.pages) + 1

        handler = JobLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        crawler_logger = logging.getLogger("crawler")
        crawler_logger.addHandler(handler)

        try:
            pages = crawler.crawl()
        finally:
            crawler_logger.removeHandler(handler)

        if not pages:
            job.status = "failed"
            job.error = "No pages found at the provided URL. The site may be unreachable or JavaScript-only."
            job.completed_at = time.time()
            return

        job.pages_found = len(pages)
        job.add_message(f"Crawl complete: {len(pages)} pages found")

        # Phase 2: Convert to PDF
        job.status = "converting"
        job.add_message("Generating PDF...")

        output_filename = f"{job.job_id}.pdf"
        output_path = str(OUTPUT_DIR / output_filename)

        generator = DocumentationPDFGenerator(config)
        success = generator.generate(
            pages=pages,
            output_path=output_path,
            add_toc=True,
        )

        if success:
            job.status = "completed"
            job.output_path = output_path
            job.pages_processed = len(pages)
            size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            job.add_message(f"PDF generated: {size_mb:.1f} MB, {len(pages)} pages")
        else:
            job.status = "failed"
            job.error = "PDF generation failed. Check logs for details."

    except Exception as e:
        logger.exception(f"Conversion failed for job {job.job_id}")
        job.status = "failed"
        job.error = str(e)

    finally:
        job.completed_at = time.time()


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def start_conversion():
    """Start a new URL-to-PDF conversion job."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    # Optional parameters
    max_depth = min(int(data.get("max_depth", 10)), 50)
    delay = max(float(data.get("delay", 0.5)), 0.1)
    use_javascript = bool(data.get("javascript", False))

    # Create configuration
    config = CrawlerConfig(
        base_url=url,
        max_depth=max_depth,
        request_delay=delay,
    )

    # Create job
    job_id = str(uuid.uuid4())[:8]
    job = ConversionJob(job_id, url, config)
    jobs[job_id] = job

    # Start conversion in background thread
    thread = threading.Thread(
        target=run_conversion,
        args=(job,),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": f"Conversion started for {url}",
    })


@app.route("/status/<job_id>")
def get_status(job_id: str):
    """Get the status of a conversion job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict())


@app.route("/stream/<job_id>")
def stream_status(job_id: str):
    """Stream job status updates via Server-Sent Events (SSE)."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        last_msg_count = 0
        while True:
            current_data = job.to_dict()
            current_msg_count = len(job.progress_messages)

            # Only send if there are new messages or status changed
            if current_msg_count > last_msg_count or job.status in ("completed", "failed"):
                yield f"data: {json.dumps(current_data)}\n\n"
                last_msg_count = current_msg_count

            if job.status in ("completed", "failed"):
                break

            time.sleep(1)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/download/<job_id>")
def download_pdf(job_id: str):
    """Download the generated PDF."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status != "completed":
        return jsonify({"error": "PDF not ready yet"}), 400

    if not job.output_path or not Path(job.output_path).exists():
        return jsonify({"error": "PDF file not found"}), 404

    # Generate a friendly filename from the URL
    from urllib.parse import urlparse
    parsed = urlparse(job.url)
    friendly_name = parsed.netloc.replace(".", "_")
    path_part = parsed.path.strip("/").replace("/", "_")
    if path_part:
        friendly_name += f"_{path_part}"
    friendly_name = friendly_name[:80]  # Limit length

    return send_file(
        job.output_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{friendly_name}.pdf",
    )


def main():
    """Run the Flask development server."""
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    logger.info(f"Starting Web2PDF server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
