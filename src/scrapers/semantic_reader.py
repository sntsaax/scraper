import json
import os
from typing import List

from playwright.sync_api import sync_playwright

from src.benchmark_profile import SiteProfile
from src.scrapers.base import BaseScraper
from src.schemas import JobListing
from src.utils.logger import get_logger


logger = get_logger(__name__)


class SemanticReaderScraper(BaseScraper):
    """LLM-based semantic extraction using Claude."""

    def __init__(self):
        super().__init__()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.available = False
        self.client = None
        self.fallback_mode = False

        if not api_key or api_key == "your_anthropic_key_here":
            # Allow a local heuristic fallback so the semantic scraper can still participate
            # in benchmarks even when an LLM key is not available. This makes comparison
            # between methods easier during development.
            logger.warning(
                "SemanticReader: ANTHROPIC_API_KEY not set. Enabling heuristic fallback mode."
            )
            self.available = True
            self.fallback_mode = True
            return

        try:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=api_key)
            self.available = True
            logger.info("SemanticReader: Initialized successfully")
        except Exception as e:
            logger.warning(f"SemanticReader: Failed to initialize: {e}")

    def _parse_response(self, response_text: str):
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            if "```" in response_text:
                json_str = response_text.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                return json.loads(json_str.strip())
            raise

    def extract(self, site: SiteProfile) -> List[JobListing]:
        """Extract job listings using semantic LLM analysis."""
        results: List[JobListing] = []
        self._last_run_metrics = {
            "model": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "fallback_used": False,
        }

        if not self.available:
            logger.warning("SemanticReader: Not available, returning empty results")
            return results

        raw_html = None
        raw_text = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(site.benchmark_url(), wait_until="load")

                try:
                    for cookie_selector in site.cookie_selectors:
                        try:
                            page.click(cookie_selector, timeout=3000)
                            logger.info("Cookie banner dismissed.")
                            break
                        except Exception:
                            continue
                except Exception:
                    logger.warning("No cookie banner found.")

                page.wait_for_selector("body", timeout=5000)
                raw_html = page.content()
                raw_text = page.locator("body").inner_text()
                browser.close()

            logger.info("Page content fetched successfully.")

        except Exception as e:
            logger.error(f"Failed to fetch page: {e}")
            return results

        if not raw_html:
            logger.error("No HTML content retrieved")
            return results

        try:
            payload = raw_html[: site.semantic_max_chars]
            text_payload = (raw_text or "")[: site.semantic_max_chars]
            extraction_prompt = f"""You are an expert at extracting structured data from dynamic job pages.

Your task is to extract ALL job listings from the provided page content and return them as a JSON array.

SCHEMA:
[
  {{
    "title": "string (job title)",
    "company": "string (company name)",
    "location": "string (location)",
    "url": "string (full URL to job post)",
    "description": "string or null (job description if available)"
  }}
]

RULES:
- Return ONLY valid JSON, no markdown, no explanation
- Use null for missing fields
- Do NOT infer values not visible in the HTML
- Do NOT include extra fields
- Ensure all URLs are complete (with https://)
- Return empty array [] if no job listings found

PAGE TEXT:
{text_payload}

HTML Content:
{payload}

Return only the JSON array:"""

            # If running with a real Anthropic client, use the LLM extraction path.
            if not self.fallback_mode and self.client:
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": extraction_prompt}],
                )

                response_text = response.content[0].text.strip()
                logger.info(f"Claude response received: {len(response_text)} chars")

                usage = getattr(response, "usage", None)
                if usage:
                    self._last_run_metrics["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
                    self._last_run_metrics["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
                self._last_run_metrics["model"] = "claude-3-5-sonnet-20241022"

                try:
                    parsed = self._parse_response(response_text)
                except Exception:
                    self._last_run_metrics["fallback_used"] = True
                    parsed = []

                if not isinstance(parsed, list):
                    parsed = [parsed] if parsed else []

                for item in parsed:
                    try:
                        job = JobListing(**item)
                        results.append(job)
                    except Exception as e:
                        logger.warning(f"Skipping invalid record: {e}")

                logger.info(f"Extracted {len(results)} job listings via LLM.")
            else:
                # Heuristic fallback: reuse rule-based selectors to approximate semantic extraction.
                logger.info("SemanticReader: running heuristic fallback extraction (no LLM key)")
                from src.scrapers.rule_follower import RuleFollowerScraper

                rf = RuleFollowerScraper()
                results = rf.extract(site)
                # mark fallback metrics
                self._last_run_metrics["fallback_used"] = True
                self._last_run_metrics["method"] = "rule_follower_fallback"
                logger.info(f"Heuristic fallback extracted {len(results)} job listings.")

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")

        return results
