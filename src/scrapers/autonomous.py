import json
from typing import List, Optional
from playwright.sync_api import sync_playwright
from src.scrapers.base import BaseScraper
from src.schemas import JobListing
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AutonomousScraper(BaseScraper):
    """
    Autonomous browser agent that interacts with the page to extract job listings.
    Uses browser automation with observation and action cycles.
    """

    def __init__(self):
        self.url = (
            "https://mellby-gaard.se/om-oss/karriarssida"
            "?searchWord=&sourceName=&city=&page=0"
        )
        self.max_interactions = 10

    def extract(self) -> List[JobListing]:
        """Extract job listings using autonomous browser interaction."""
        results = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.url, wait_until="load")

                logger.info("Page loaded, starting autonomous extraction...")

                # Step 1: Handle cookie banner (observation + action)
                try:
                    cookie_button = page.query_selector("button:has-text('Acceptera')")
                    if cookie_button:
                        logger.info("Autonomous: Found and clicking cookie banner...")
                        page.click("button:has-text('Acceptera')", timeout=3000)
                except Exception as e:
                    logger.warning(f"Autonomous: Cookie handling failed: {e}")

                # Step 2: Observe page structure
                logger.info("Autonomous: Observing page structure...")
                selector = "a:has(.career-page__job--inner-container)"

                # Step 3: Wait for content
                try:
                    page.wait_for_selector(selector, timeout=5000)
                except Exception:
                    logger.warning("Autonomous: Job cards selector not found, trying alternatives...")
                    # Try alternative selectors for different page structures
                    alt_selectors = [
                        "div[class*='job']",
                        "article",
                        "li[class*='job']",
                    ]
                    selector = None
                    for alt_sel in alt_selectors:
                        try:
                            page.wait_for_selector(alt_sel, timeout=2000)
                            selector = alt_sel
                            logger.info(f"Autonomous: Found alternative selector: {alt_sel}")
                            break
                        except Exception:
                            continue

                    if not selector:
                        logger.error("Autonomous: No job listing selectors found")
                        browser.close()
                        return results

                # Step 4: Scroll to load more content (if needed)
                logger.info("Autonomous: Scrolling to load content...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                # Step 5: Extract all visible job cards
                logger.info("Autonomous: Extracting visible job listings...")
                job_cards = page.query_selector_all(selector)
                logger.info(f"Autonomous: Found {len(job_cards)} job cards")

                for idx, card in enumerate(job_cards):
                    try:
                        # Try standard selectors first
                        title_el = card.query_selector(
                            ".career-page__job--text--title"
                        )
                        loc_el = card.query_selector(
                            ".career-page__job--text--location"
                        )

                        title = title_el.inner_text().strip() if title_el else ""
                        location = loc_el.inner_text().strip() if loc_el else ""
                        url = card.get_attribute("href") or ""

                        # Make URL absolute if needed
                        if url and not url.startswith("http"):
                            url = f"https://mellby-gaard.se{url}"

                        if title and url:  # Require at least title and URL
                            job = JobListing(
                                title=title,
                                company="Mellby Gård",
                                location=location,
                                url=url,
                            )
                            results.append(job)
                            logger.info(f"Autonomous: Extracted job {idx + 1}: {title}")

                    except Exception as e:
                        logger.warning(f"Autonomous: Failed to extract card {idx}: {e}")

                # Step 6: Try to interact with pagination if available
                logger.info("Autonomous: Checking for pagination...")
                next_button = page.query_selector("button[aria-label*='next'], a[rel='next']")
                if next_button and len(results) < 50:  # Safety limit
                    try:
                        logger.info("Autonomous: Found next button, attempting click...")
                        page.click("button[aria-label*='next'], a[rel='next']")
                        page.wait_for_load_state("load", timeout=3000)
                        # Could recursively extract more, but keep it simple for thesis
                        logger.info("Autonomous: Pagination attempted (limited to 1 page)")
                    except Exception as e:
                        logger.info(f"Autonomous: Pagination failed: {e}")

                browser.close()

        except Exception as e:
            logger.error(f"Autonomous extraction failed: {e}")

        logger.info(f"Autonomous: Extracted {len(results)} total jobs.")
        return results
