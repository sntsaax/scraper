from abc import ABC, abstractmethod
from typing import Any, Dict, List
from src.benchmark_profile import SiteProfile
from src.schemas import JobListing


class BaseScraper(ABC):
    def __init__(self):
        self._last_run_metrics: Dict[str, Any] = {}

    @abstractmethod
    def extract(self, site: SiteProfile) -> List[JobListing]:
        pass

    def get_run_metrics(self) -> Dict[str, Any]:
        return dict(self._last_run_metrics)
