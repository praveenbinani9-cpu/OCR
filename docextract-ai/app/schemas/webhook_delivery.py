from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    url: str
    response_status: int | None = None
    response_body: str | None = None
    attempt_count: int
    delivered_at: datetime | None = None
    created_at: datetime


class WebhookDeliveryPage(BaseModel):
    items: List[WebhookDeliveryOut]
    total: int
    page: int
    page_size: int
