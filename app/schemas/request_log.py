from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RequestLogEntry(BaseModel):
    requested_at: datetime
    method: str
    path: str
    query_string: Optional[str] = None
    route: Optional[str] = None
    status_code: int
    duration_ms: float
    client_host: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = {"from_attributes": True}


class RequestLogListResponse(BaseModel):
    total: int
    entries: list[RequestLogEntry]
