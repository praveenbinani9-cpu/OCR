from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_size: int
    mime_type: str
    status: str
    created_at: datetime


class DocumentPage(BaseModel):
    items: List[DocumentOut]
    total: int
    page: int
    page_size: int
