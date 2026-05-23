import json
from typing import List, Optional
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from src.scrapers.base import BaseScraper
from src.benchmark_profile import SiteProfile
from src.schemas import JobListing
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AutonomousScraper(BaseScraper):
    """
    Autonomous browser agent that interacts with the page to extract job listings.
    Uses browser automation with observation and action cycles.
    """

    def __init__(self):
        super().__init__()
        self.max_interactions = 10

    def extract(self, site: SiteProfile) -> List[JobListing]:
        """Extract job listings using autonomous browser interaction."""
        results = []
        fallback_used = False
        selector_used = None
        cards_found = 0
        interactions = 0
        seen_urls = set()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(site.benchmark_url(), wait_until="load")

                logger.info("Page loaded, starting autonomous extraction...")

                try:
                    for cookie_selector in site.cookie_selectors:
                        cookie_button = page.query_selector(cookie_selector)
                        if cookie_button:
                            logger.info("Autonomous: Found and clicking cookie banner...")
                            page.click(cookie_selector, timeout=3000)
                            interactions += 1
                            break
                except Exception as e:
                    logger.warning(f"Autonomous: Cookie handling failed: {e}")

                logger.info("Autonomous: Observing page structure...")
                selector_candidates = list(site.item_selectors)
                selector_candidates.extend([
                    "a[href*='/karriar']",
                    "article",
                    "li[class*='job']",
                    "div[class*='job']",
                ])

                try:
                    for candidate in selector_candidates:
                        try:
                            page.wait_for_selector(candidate, timeout=2500)
                            selector_used = candidate
                            break
                        except Exception:
                            fallback_used = True
                            continue
                    if not selector_used:
                        raise RuntimeError("No job listing selectors found")
                except Exception:
                    logger.warning("Autonomous: Job cards selector not found, trying alternatives...")
                    selector_used = "a[href]"
                    fallback_used = True

                logger.info("Autonomous: Scrolling to load content...")
                for _ in range(max(site.max_scrolls, 1)):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    interactions += 1

                logger.info("Autonomous: Extracting visible job listings...")
                job_cards = page.query_selector_all(selector_used)
                if not job_cards:
                    job_cards = page.query_selector_all("a[href]")
                    selector_used = "a[href]"
                    fallback_used = True
                cards_found = len(job_cards)
                logger.info(f"Autonomous: Found {len(job_cards)} job cards")

                for idx, card in enumerate(job_cards):
                    try:
                        title_el = card.query_selector(site.title_selector)
                        loc_el = card.query_selector(site.location_selector)

                        if not title_el:
                            title_el = card.query_selector("h1, h2, h3, .title, .job-title")
                        if not loc_el:
                            loc_el = card.query_selector(".location, [data-location]")

                        title = title_el.inner_text().strip() if title_el else ""
                        location = loc_el.inner_text().strip() if loc_el else ""
                        href = card.get_attribute("href") or ""
                        if not href:
                            link_el = card.query_selector(
                                "a[href*='jobid'], a[href*='lediga-jobb'], a[href*='studentconsulting'], a[href*='academedia'], a[href]"
                            )
                            if link_el:
                                href = link_el.get_attribute("href") or ""

                        url = urljoin(site.url, href) if href else ""

                        if title and url and url not in seen_urls:
                            job = JobListing(
                                title=title,
                                company=site.company_name,
                                location=location,
                                url=url,
                            )
                            results.append(job)
                            seen_urls.add(url)
                            logger.info(f"Autonomous: Extracted job {idx + 1}: {title}")

                    except Exception as e:
                        logger.warning(f"Autonomous: Failed to extract card {idx}: {e}")

                logger.info("Autonomous: Checking for pagination...")
                next_button = page.query_selector("button[aria-label*='next'], a[rel='next']")
                if next_button and len(results) < 50:  # Safety limit
                    try:
                        logger.info("Autonomous: Found next button, attempting click...")
                        page.click("button[aria-label*='next'], a[rel='next']")
                        page.wait_for_load_state("load", timeout=3000)
                        interactions += 1
                        logger.info("Autonomous: Pagination attempted (limited to 1 page)")
                    except Exception as e:
                        logger.info(f"Autonomous: Pagination failed: {e}")

                browser.close()

        except Exception as e:
            logger.error(f"Autonomous extraction failed: {e}")

        self._last_run_metrics = {
            "selector_used": selector_used,
            "fallback_used": fallback_used,
            "cards_observed": cards_found,
            "interaction_count": interactions,
        }
        logger.info(f"Autonomous: Extracted {len(results)} total jobs.")
        return results
