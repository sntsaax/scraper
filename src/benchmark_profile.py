from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import json
import os


@dataclass(frozen=True)
class SiteProfile:
    name: str
    url: str
    ground_truth_file: str
    company_name: str = "Mellby Gård"
    item_selectors: tuple[str, ...] = (
        "a:has(.career-page__job--inner-container)",
        "article",
        "li[class*='job']",
        "div[class*='job']",
    )
    title_selector: str = ".career-page__job--text--title"
    location_selector: str = ".career-page__job--text--location"
    cookie_selectors: tuple[str, ...] = ("button:has-text('Acceptera')",)
    semantic_max_chars: int = 12000
    max_scrolls: int = 1
    expected_record_count: Optional[int] = None

    def ground_truth_path(self) -> Path:
        return Path(self.ground_truth_file)


DEFAULT_SITE_PROFILE = SiteProfile(
    name=os.getenv("BENCHMARK_SITE_NAME", "mellby_gaard_careers"),
    url=os.getenv(
        "BENCHMARK_SITE_URL",
        "https://mellby-gaard.se/om-oss/karriarssida?searchWord=&sourceName=&city=&page=0",
    ),
    ground_truth_file=os.getenv("BENCHMARK_GROUND_TRUTH_FILE", "data/ground_truth.json"),
    expected_record_count=int(os.getenv("BENCHMARK_EXPECTED_RECORDS", "20")),
)


def load_site_profiles() -> List[SiteProfile]:
    """Load site profiles from JSON or return the default benchmark site."""
    config_path = os.getenv("BENCHMARK_SITE_PROFILES")
    if not config_path:
        return [DEFAULT_SITE_PROFILE]

    path = Path(config_path)
    if not path.exists():
        return [DEFAULT_SITE_PROFILE]

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw_profiles = json.load(handle)
        profiles: List[SiteProfile] = []
        for raw_profile in raw_profiles:
            profiles.append(
                SiteProfile(
                    name=raw_profile.get("name", DEFAULT_SITE_PROFILE.name),
                    url=raw_profile.get("url", DEFAULT_SITE_PROFILE.url),
                    ground_truth_file=raw_profile.get(
                        "ground_truth_file", DEFAULT_SITE_PROFILE.ground_truth_file
                    ),
                    company_name=raw_profile.get(
                        "company_name", DEFAULT_SITE_PROFILE.company_name
                    ),
                    item_selectors=tuple(
                        raw_profile.get("item_selectors", DEFAULT_SITE_PROFILE.item_selectors)
                    ),
                    title_selector=raw_profile.get(
                        "title_selector", DEFAULT_SITE_PROFILE.title_selector
                    ),
                    location_selector=raw_profile.get(
                        "location_selector", DEFAULT_SITE_PROFILE.location_selector
                    ),
                    cookie_selectors=tuple(
                        raw_profile.get("cookie_selectors", DEFAULT_SITE_PROFILE.cookie_selectors)
                    ),
                    semantic_max_chars=int(
                        raw_profile.get(
                            "semantic_max_chars", DEFAULT_SITE_PROFILE.semantic_max_chars
                        )
                    ),
                    max_scrolls=int(raw_profile.get("max_scrolls", DEFAULT_SITE_PROFILE.max_scrolls)),
                    expected_record_count=raw_profile.get(
                        "expected_record_count", DEFAULT_SITE_PROFILE.expected_record_count
                    ),
                )
            )
        return profiles or [DEFAULT_SITE_PROFILE]
    except Exception:
        return [DEFAULT_SITE_PROFILE]
