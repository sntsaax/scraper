from pydantic import BaseModel
from typing import Optional


class JobListing(BaseModel):
    title: str
    company: str
    location: str
    url: str
    description: Optional[str] = None
