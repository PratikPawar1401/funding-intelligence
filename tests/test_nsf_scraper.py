"""Tests for the NSF web scraper module.

Tests the pure-function HTML parsing logic — no network calls needed.
Covers:
- HTML content parsing (_parse_html_content)
- Date extraction from HTML (_extract_dates_from_html)
- NSF ID extraction from URLs (_extract_nsf_id)
- Playwright scraper mock execution
- Database queue draining
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bs4 import BeautifulSoup

from foa_pipeline.config import Config
from foa_pipeline.nsf_scraper import (
    _extract_dates_from_html,
    _extract_nsf_id,
    _parse_html_content,
    _run_playwright_scraper,
    drain_nsf_queue,
)

# ═══════════════════════════════════════════════
# _extract_nsf_id tests
# ═══════════════════════════════════════════════


class TestExtractNsfId:
    def test_solicitation_number(self):
        url = "https://www.nsf.gov/funding/opportunities/nsf-25-578"
        assert _extract_nsf_id(url) == "NSF-25-578"

    def test_program_number(self):
        url = "https://www.nsf.gov/funding/opportunities/24-1234"
        assert _extract_nsf_id(url) == "NSF-24-1234"

    def test_fallback_path(self):
        url = "https://www.nsf.gov/funding/opportunities/climate-research"
        assert _extract_nsf_id(url) == "climate-research"

    def test_trailing_slash(self):
        url = "https://www.nsf.gov/funding/opportunities/some-program/"
        assert _extract_nsf_id(url) == "some-program"


# ═══════════════════════════════════════════════
# _extract_dates_from_html tests
# ═══════════════════════════════════════════════


class TestExtractDatesFromHtml:
    def test_deadline_extraction(self):
        html = "<div>Deadline: September 30, 2025</div>"
        soup = BeautifulSoup(html, "html.parser")
        dates = _extract_dates_from_html(soup)
        assert dates["close_date"] is not None
        assert "September" in dates["close_date"]

    def test_posted_date_extraction(self):
        html = "<div>Posted: June 15, 2025</div>"
        soup = BeautifulSoup(html, "html.parser")
        dates = _extract_dates_from_html(soup)
        assert dates["posted_date"] is not None
        assert "June" in dates["posted_date"]

    def test_due_date_extraction(self):
        html = "<div>Due Date: March 1, 2026</div>"
        soup = BeautifulSoup(html, "html.parser")
        dates = _extract_dates_from_html(soup)
        assert dates["close_date"] is not None

    def test_no_dates(self):
        html = "<div>No date information here.</div>"
        soup = BeautifulSoup(html, "html.parser")
        dates = _extract_dates_from_html(soup)
        assert dates["close_date"] is None
        assert dates["posted_date"] is None


# ═══════════════════════════════════════════════
# _parse_html_content tests
# ═══════════════════════════════════════════════


class TestParseHtmlContent:
    def test_extracts_title(self):
        html = "<html><body><h1>Climate Research Program</h1></body></html>"
        result = _parse_html_content("https://nsf.gov/test", html)
        assert result["title"] == "Climate Research Program"

    def test_extracts_description(self):
        html = """
        <html><body>
            <h1>Test</h1>
            <div class="program-description">
                This program funds innovative climate research.
            </div>
        </body></html>
        """
        result = _parse_html_content("https://nsf.gov/test", html)
        assert "climate research" in result["program_description"].lower()

    def test_extracts_pdf_links(self):
        html = """
        <html><body>
            <h1>Test</h1>
            <a href="/documents/solicitation.pdf">Download PDF</a>
            <a href="https://nsf.gov/files/guide.pdf">Guide</a>
            <a href="/page.html">Not a PDF</a>
        </body></html>
        """
        result = _parse_html_content("https://nsf.gov/test", html)
        assert len(result["pdf_links"]) == 2
        # Relative PDF links should be made absolute
        assert all(link.startswith("http") for link in result["pdf_links"])

    def test_no_title(self):
        html = "<html><body><p>No heading here</p></body></html>"
        result = _parse_html_content("https://nsf.gov/test", html)
        assert result["title"] is None

    def test_source_fields(self):
        html = "<html><body><h1>Test</h1></body></html>"
        result = _parse_html_content("https://nsf.gov/funding/opportunities/25-578", html)
        assert result["source"] == "nsf_scraper"
        assert result["source_url"] == "https://nsf.gov/funding/opportunities/25-578"
        assert result["source_id"] == "NSF-25-578"

    def test_fallback_description_from_main(self):
        html = """
        <html><body>
            <h1>Test</h1>
            <main>
                This is the main content area with program details.
            </main>
        </body></html>
        """
        result = _parse_html_content("https://nsf.gov/test", html)
        assert "program details" in result["program_description"].lower()


# ═══════════════════════════════════════════════
# Playwright and Queue draining mock tests
# ═══════════════════════════════════════════════

class TestPlaywrightScraper:
    @pytest.mark.asyncio
    @patch("foa_pipeline.nsf_scraper.async_playwright")
    async def test_run_playwright_scraper_success(self, mock_async_playwright):
        # Mock setup
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html><body><h1>Success</h1></body></html>"

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        mock_p = AsyncMock()
        mock_p.chromium.launch.return_value = mock_browser

        # async with async_playwright() as p:
        mock_async_playwright.return_value.__aenter__.return_value = mock_p

        urls = ["https://nsf.gov/test1", "https://nsf.gov/test2"]
        results = await _run_playwright_scraper(urls, max_concurrent=1)

        assert len(results) == 2
        assert "https://nsf.gov/test1" in results
        assert results["https://nsf.gov/test1"]["title"] == "Success"

        # Verify calls
        assert mock_page.goto.call_count == 2
        assert mock_page.content.call_count == 2
        assert mock_browser.close.call_count == 1


class TestDrainNsfQueue:
    @pytest.fixture
    def setup_queue_db(self, test_config):
        # Setup an SQLite queue db
        conn = sqlite3.connect(str(test_config.sqlite_db_path))
        conn.execute("CREATE TABLE pending_urls (url TEXT PRIMARY KEY, status TEXT, scraped_at TEXT)")
        conn.execute("INSERT INTO pending_urls (url, status) VALUES ('https://nsf.gov/test_db', 'pending')")
        conn.commit()
        conn.close()
        return test_config

    @patch("foa_pipeline.nsf_scraper._run_playwright_scraper", new_callable=AsyncMock)
    def test_drain_nsf_queue_success(self, mock_run, setup_queue_db):
        config = setup_queue_db

        # Mock scraper result
        mock_run.return_value = {
            "https://nsf.gov/test_db": {
                "source_id": "test_db",
                "title": "DB Test",
            }
        }

        stats = drain_nsf_queue(config)

        assert stats["total_pending"] == 1
        assert stats["scraped"] == 1
        assert stats["failed"] == 0

        # Verify db updated
        conn = sqlite3.connect(str(config.sqlite_db_path))
        row = conn.execute("SELECT status FROM pending_urls WHERE url='https://nsf.gov/test_db'").fetchone()
        conn.close()

        assert row[0] == "scraped"

    def test_drain_nsf_queue_dry_run(self, setup_queue_db):
        config = setup_queue_db

        stats = drain_nsf_queue(config, dry_run=True)

        assert stats["total_pending"] == 1
        assert stats["skipped"] == 1

        # Verify db NOT updated
        conn = sqlite3.connect(str(config.sqlite_db_path))
        row = conn.execute("SELECT status FROM pending_urls WHERE url='https://nsf.gov/test_db'").fetchone()
        conn.close()

        assert row[0] == "pending"

    @patch("foa_pipeline.nsf_scraper._run_playwright_scraper", new_callable=AsyncMock)
    def test_drain_nsf_queue_failed(self, mock_run, setup_queue_db):
        config = setup_queue_db

        # Mock scraper result - no data returned for the URL
        mock_run.return_value = {}

        stats = drain_nsf_queue(config)

        assert stats["total_pending"] == 1
        assert stats["scraped"] == 0
        assert stats["failed"] == 1

        # Verify db updated to failed
        conn = sqlite3.connect(str(config.sqlite_db_path))
        row = conn.execute("SELECT status FROM pending_urls WHERE url='https://nsf.gov/test_db'").fetchone()
        conn.close()

        assert row[0] == "failed"
