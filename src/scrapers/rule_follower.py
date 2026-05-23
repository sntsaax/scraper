from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
from src.scrapers.base import BaseScraper
from src.benchmark_profile import SiteProfile
from src.schemas import JobListing
from src.utils.logger import get_logger
from typing import List

logger = get_logger(__name__)


class RuleFollowerScraper(BaseScraper):
    def extract(self, site: SiteProfile) -> List[JobListing]:
        results = []
        fallback_used = False
        selector_used = None
        seen_urls = set()
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
                else:
                    logger.warning("No cookie banner found.")
            except Exception:
                logger.warning("No cookie banner found.")

            selector_candidates = list(site.item_selectors)
            selector_candidates.extend([
                "a[href*='/karriar']",
                "article",
                "li",
                "div[class*='job']",
            ])

            job_cards = []
            for candidate in selector_candidates:
                try:
                    page.wait_for_selector(candidate, timeout=3000)
                    job_cards = page.query_selector_all(candidate)
                    selector_used = candidate
                    break
                except Exception:
                    fallback_used = True
                    continue

            if not job_cards:
                logger.warning("RuleFollower: No selectors matched, falling back to link scan.")
                fallback_used = True
                job_cards = page.query_selector_all("a[href]")
                selector_used = "a[href]"

            for card in job_cards:
                try:
                    title_el = card.query_selector(site.title_selector)
                    loc_el = card.query_selector(site.location_selector)

                    if not title_el:
                        title_el = card.query_selector("h1, h2, h3, .title, .job-title")
                    if not loc_el:
                        loc_el = card.query_selector(".location, [data-location]")

                    title = (
                        title_el.inner_text().strip()
                        if title_el
                        else card.inner_text().splitlines()[0].strip()
                        if card.inner_text().splitlines()
                        else "N/A"
                    )
                    location = loc_el.inner_text().strip() if loc_el else "N/A"
                    href = card.get_attribute("href") or ""
                    if not href:
                        link_el = card.query_selector(
                            "a[href*='jobid'], a[href*='lediga-jobb'], a[href*='studentconsulting'], a[href*='academedia'], a[href]"
                        )
                        if link_el:
                            href = link_el.get_attribute("href") or ""

                    url = urljoin(site.url, href) if href else ""

                    job = JobListing(
                        title=title,
                        company=site.company_name,
                        location=location,
                        url=url,
                    )
                    if job.title and job.url and job.url not in seen_urls:
                        results.append(job)
                        seen_urls.add(job.url)
                except Exception as e:
                    logger.error(f"Skipping card: {e}")

            browser.close()
        self._last_run_metrics = {
            "selector_used": selector_used,
            "fallback_used": fallback_used,
            "cards_observed": len(job_cards),
        }
        logger.info(f"Scraped {len(results)} jobs.")
        return results
