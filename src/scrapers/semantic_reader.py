import json
import os
from typing import List, Optional
from playwright.sync_api import sync_playwright
from src.scrapers.base import BaseScraper
from src.schemas import JobListing
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SemanticReaderScraper(BaseScraper):
    """
    LLM-based semantic extraction using Claude.
    Extracts job listings by analyzing page content without relying on selectors.
    """

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.available = False
        
        if not api_key or api_key == "your_anthropic_key_here":
            logger.warning("SemanticReader: ANTHROPIC_API_KEY not set. This scraper will be skipped.")
            return
        
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key)
            self.available = True
            logger.info("SemanticReader: Initialized successfully")
        except Exception as e:
            logger.warning(f"SemanticReader: Failed to initialize: {e}")
            
        self.url = (
            "https://mellby-gaard.se/om-oss/karriarssida"
            "?searchWord=&sourceName=&city=&page=0"
        )

    def extract(self) -> List[JobListing]:
        """Extract job listings using semantic LLM analysis."""
        results = []
        
        if not self.available:
            logger.warning("SemanticReader: API key not configured, returning empty results")
            return results
        
        raw_html = None

        try:
            # Fetch page content with browser
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.url, wait_until="load")

                # Handle cookie banner
                try:
                    page.click("button:has-text('Acceptera')", timeout=3000)
                    logger.info("Cookie banner dismissed.")
                except Exception:
                    logger.warning("No cookie banner found.")

                # Wait for content
                page.wait_for_selector("body", timeout=5000)
                raw_html = page.content()
                browser.close()

            logger.info("Page content fetched successfully.")

        except Exception as e:
            logger.error(f"Failed to fetch page: {e}")
            return results

        if not raw_html:
            logger.error("No HTML content retrieved")
            return results

        # Send to Claude for extraction
        try:
            extraction_prompt = f"""You are an expert at extracting structured data from HTML.

Your task is to extract ALL job listings from this HTML and return them as a JSON array.

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

HTML Content:
{raw_html[:8000]}

Return only the JSON array:"""

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=[{"role": "user", "content": extraction_prompt}],
            )

            response_text = response.content[0].text.strip()
            logger.info(f"Claude response received: {len(response_text)} chars")

            # Parse JSON response
            try:
                # Try direct parsing first
                parsed = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON if wrapped in markdown
                if "```" in response_text:
                    json_str = response_text.split("```")[1]
                    if json_str.startswith("json"):
                        json_str = json_str[4:]
                    parsed = json.loads(json_str.strip())
                else:
                    raise

            # Convert to JobListing objects
            if not isinstance(parsed, list):
                parsed = [parsed] if parsed else []

            for item in parsed:
                try:
                    job = JobListing(**item)
                    results.append(job)
                except Exception as e:
                    logger.warning(f"Skipping invalid record: {e}")

            logger.info(f"Extracted {len(results)} job listings.")

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")

        return results
