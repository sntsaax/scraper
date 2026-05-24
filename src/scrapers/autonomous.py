from typing import Dict, List
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
    Uses browser automation with observation, planning, and action cycles.
    """

    def __init__(self):
        super().__init__()
        self.max_interactions = 12
        self._job_keywords = ("job", "career", "position", "role", "vacancy", "opening")

    def _dedupe(self, values: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered.append(cleaned)
        return ordered

    def _score_selector(self, page, selector: str) -> float:
        try:
            locator = page.locator(selector)
            count = locator.count()
            if count <= 0:
                return -1.0

            sample_count = min(count, 5)
            keyword_hits = 0
            link_hits = 0
            text_length_total = 0

            for index in range(sample_count):
                node = locator.nth(index)
                text = (node.inner_text(timeout=1000) or "").strip().lower()
                text_length_total += len(text)
                if any(keyword in text for keyword in self._job_keywords):
                    keyword_hits += 1
                if node.query_selector("a[href]"):
                    link_hits += 1

            average_text_length = text_length_total / sample_count if sample_count else 0
            density_bonus = 1.5 if 20 <= average_text_length <= 800 else -0.5
            count_bonus = min(count, 20) * 0.4
            keyword_bonus = keyword_hits * 2.0
            link_bonus = link_hits * 1.5

            return count_bonus + keyword_bonus + link_bonus + density_bonus
        except Exception:
            return -1.0

    def _infer_selector_candidates(self, page, site: SiteProfile) -> List[str]:
        candidates = list(site.item_selectors) + [
            "main article",
            "main li",
            "main div",
            "main a[href*='/detail/']",
            "main a[href*='/jobs/']",
            "main a[href*='/positions/']",
            "article",
            "li",
            "div[class*='job']",
            "div[class*='career']",
            "a[href*='/detail/']",
            "a[href*='/jobs/']",
            "a[href*='/positions/']",
            "a[href*='job']",
            "a[href*='career']",
            "a[href*='position']",
            "a[href*='vacan']",
            "a[href]",
            "tr",
        ]

        try:
            inferred = page.evaluate(
                """() => {
                    const roots = Array.from(document.querySelectorAll('a[href], article, li, section, tr, div'));
                    const output = [];
                    for (const node of roots.slice(0, 300)) {
                        const text = (node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                        const href = (node.getAttribute && node.getAttribute('href')) || '';
                        const cls = typeof node.className === 'string' ? node.className : '';
                        const tag = (node.tagName || '').toLowerCase();
                        if (!text && !href && !cls) {
                            continue;
                        }
                        if (!/job|career|position|role|vacan|opening/.test(`${text} ${href} ${cls}`)) {
                            continue;
                        }
                        const classToken = cls
                            .split(/\\s+/)
                            .filter(Boolean)
                            .slice(0, 2)
                            .map((part) => `.${part.replace(/[^a-zA-Z0-9_-]/g, '')}`)
                            .join('');
                        output.push(`${tag}${classToken}`);
                    }
                    return output;
                }"""
            )
            if isinstance(inferred, list):
                candidates.extend([item for item in inferred if isinstance(item, str)])
        except Exception:
            pass

        return self._dedupe(candidates)

    def _choose_best_selector(self, page, site: SiteProfile, action_log: List[str]) -> tuple[str, Dict[str, float], bool]:
        candidates = self._infer_selector_candidates(page, site)
        scored: Dict[str, float] = {}
        best_selector = "a[href]"
        best_score = -1.0

        for selector in candidates:
            score = self._score_selector(page, selector)
            scored[selector] = score
            if score > best_score:
                best_score = score
                best_selector = selector

        fallback_used = best_selector not in site.item_selectors
        action_log.append(f"selector_selected:{best_selector}")
        return best_selector, scored, fallback_used

    def _dismiss_interruptions(self, page, site: SiteProfile, action_log: List[str]) -> bool:
        selectors = list(site.cookie_selectors) + [
            "button:has-text('Accept all')",
            "button:has-text('Accept')",
            "button:has-text('Agree')",
            "button:has-text('I agree')",
            "button:has-text('Reject all')",
            "button:has-text('Close')",
        ]
        for selector in self._dedupe(selectors):
            try:
                element = page.query_selector(selector)
                if element:
                    element.click(timeout=2000)
                    action_log.append(f"cookie_clicked:{selector}")
                    page.wait_for_timeout(250)
                    return True
            except Exception:
                continue
        return False

    def _scroll_page(self, page, action_log: List[str]) -> bool:
        try:
            page.evaluate(
                """() => {
                    window.scrollBy(0, Math.max(window.innerHeight * 0.9, document.body.scrollHeight * 0.35));
                }"""
            )
            page.wait_for_timeout(400)
            action_log.append("action:scroll")
            return True
        except Exception:
            return False

    def _click_action_button(self, page, pattern: str, action_name: str, action_log: List[str]) -> bool:
        try:
            locator = page.locator(f"button:has-text('{pattern}'), a:has-text('{pattern}')")
            if locator.count() > 0:
                locator.first.click(timeout=2000)
                page.wait_for_timeout(600)
                action_log.append(f"action:{action_name}:{pattern}")
                return True
        except Exception:
            return False
        return False

    def _extract_jobs(self, page, site: SiteProfile, selector: str, seen_urls: set[str]) -> List[JobListing]:
        results: List[JobListing] = []
        job_cards = page.query_selector_all(selector)
        if not job_cards and selector != "a[href]":
            job_cards = page.query_selector_all("a[href]")
            selector = "a[href]"

        for idx, card in enumerate(job_cards):
            try:
                title_el = card.query_selector(site.title_selector)
                loc_el = card.query_selector(site.location_selector)

                if not title_el:
                    title_el = card.query_selector("h1, h2, h3, .title, .job-title, .card-title")
                if not loc_el:
                    loc_el = card.query_selector(".location, [data-location], .job-location")

                title = title_el.inner_text().strip() if title_el else ""
                location = loc_el.inner_text().strip() if loc_el else ""
                href = card.get_attribute("href") or ""

                if not href:
                    link_el = card.query_selector("a[href*='job'], a[href*='career'], a[href*='position'], a[href*='vacan'], a[href]")
                    if link_el:
                        href = link_el.get_attribute("href") or ""

                if not title:
                    try:
                        text = card.inner_text().strip()
                    except Exception:
                        text = ""
                    if text:
                        title = text.splitlines()[0].strip()

                url = urljoin(site.benchmark_url(), href) if href else ""
                relevance_source = f"{title} {href} {location}".lower()
                relevant = any(keyword in relevance_source for keyword in self._job_keywords)
                relevant = relevant or any(token in href.lower() for token in ("/detail/", "/jobs/", "/positions/", "/career"))
                if title and url and relevant and url not in seen_urls:
                    results.append(
                        JobListing(
                            title=title,
                            company=site.company_name,
                            location=location,
                            url=url,
                        )
                    )
                    seen_urls.add(url)
            except Exception as e:
                logger.warning(f"Autonomous: Failed to extract card {idx}: {e}")

        return results

    def extract(self, site: SiteProfile) -> List[JobListing]:
        """Extract job listings using autonomous browser interaction."""
        results: List[JobListing] = []
        selector_used = None
        cards_found = 0
        interactions = 0
        seen_urls: set[str] = set()
        action_log: List[str] = []
        selector_scores: Dict[str, float] = {}
        fallback_used = False
        stop_reason = "max_interactions"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(site.benchmark_url(), wait_until="domcontentloaded")

                logger.info("Page loaded, starting autonomous extraction...")

                try:
                    if self._dismiss_interruptions(page, site, action_log):
                        interactions += 1
                except Exception as e:
                    logger.warning(f"Autonomous: Cookie handling failed: {e}")

                try:
                    selector_used, selector_scores, fallback_used = self._choose_best_selector(page, site, action_log)
                except Exception:
                    logger.warning("Autonomous: Job cards selector not found, trying alternatives...")
                    selector_used = "a[href]"
                    selector_scores = {"a[href]": 0.0}
                    fallback_used = True

                logger.info(f"Autonomous: Initial selector -> {selector_used}")

                for step in range(self.max_interactions):
                    logger.info(f"Autonomous: Observation/action step {step + 1}/{self.max_interactions}")
                    batch = self._extract_jobs(page, site, selector_used, seen_urls)
                    if batch:
                        results.extend(batch)
                        logger.info(f"Autonomous: Batch extracted {len(batch)} jobs")

                    if site.expected_record_count and len(results) >= site.expected_record_count:
                        stop_reason = "expected_record_count_reached"
                        break

                    if self._dismiss_interruptions(page, site, action_log):
                        interactions += 1
                        continue

                    if self._click_action_button(page, "Load more", "load_more", action_log):
                        interactions += 1
                        selector_used, selector_scores, fallback_used = self._choose_best_selector(page, site, action_log)
                        continue
                    if self._click_action_button(page, "Show more", "show_more", action_log):
                        interactions += 1
                        selector_used, selector_scores, fallback_used = self._choose_best_selector(page, site, action_log)
                        continue
                    if self._click_action_button(page, "Next", "next_page", action_log):
                        interactions += 1
                        selector_used, selector_scores, fallback_used = self._choose_best_selector(page, site, action_log)
                        continue

                    if step < max(site.max_scrolls, 1) or len(batch) == 0:
                        if self._scroll_page(page, action_log):
                            interactions += 1
                            selector_used, selector_scores, fallback_used = self._choose_best_selector(page, site, action_log)
                            continue

                    stop_reason = "no_new_actions"
                    break

                cards_found = len(seen_urls)
                logger.info(f"Autonomous: Found {len(results)} unique job listings")
                logger.info(f"Autonomous: Stop reason: {stop_reason}")

                browser.close()

        except Exception as e:
            logger.error(f"Autonomous extraction failed: {e}")

        self._last_run_metrics = {
            "selector_used": selector_used,
            "selector_scores": selector_scores,
            "fallback_used": fallback_used,
            "cards_observed": cards_found,
            "interaction_count": interactions,
            "action_log": action_log,
            "stop_reason": stop_reason,
            "agentic_mode": "local_policy_loop",
        }
        logger.info(f"Autonomous: Extracted {len(results)} total jobs.")
        return results
