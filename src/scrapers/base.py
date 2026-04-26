from abc import ABC, abstractmethod
from typing import List
from src.schemas import JobListing


class BaseScraper(ABC):
    @abstractmethod
    def extract(self) -> List[JobListing]:
        pass
