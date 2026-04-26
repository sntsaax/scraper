from playwright.sync_api import sync_playwright
from src.scrapers.base import BaseScraper
from src.schemas import JobListing
from src.utils.logger import get_logger
from typing import List

logger = get_logger(__name__)


class RuleFollowerScraper(BaseScraper):
    def extract(self) -> List[JobListing]:
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            url = (
                "https://mellby-gaard.se/om-oss/karriarssida"
                "?searchWord=&sourceName=&city=&page=0"
            )
            page.goto(url)

            # Handle Cookie Banner
            try:
                page.click("button:has-text('Acceptera')", timeout=3000)
                logger.info("Cookie banner dismissed.")
            except Exception:
                logger.warning("No cookie banner found.")

            # Wait for content
            selector = "a:has(.career-page__job--inner-container)"
            page.wait_for_selector(selector)
            job_cards = page.query_selector_all(selector)

            for card in job_cards:
                try:
                    title_el = card.query_selector(
                        ".career-page__job--text--title"
                    )
                    loc_el = card.query_selector(
                        ".career-page__job--text--location"
                    )

                    job = JobListing(
                        title=title_el.inner_text().strip()
                        if title_el else "N/A",
                        company="Mellby Gård",
                        location=loc_el.inner_text().strip()
                        if loc_el else "N/A",
                        url=card.get_attribute("href") or "",
                    )
                    results.append(job)
                except Exception as e:
                    logger.error(f"Skipping card: {e}")

            browser.close()
        logger.info(f"Scraped {len(results)} jobs.")
        return results
