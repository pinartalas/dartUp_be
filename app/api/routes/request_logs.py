from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.core.request_logging import request_log_store
from app.models.user import User
from app.schemas.request_log import RequestLogEntry, RequestLogListResponse

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/request-logs", response_model=RequestLogListResponse)
def list_request_logs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    current_user: User = Depends(get_current_user),
):
    entries = [
        RequestLogEntry.model_validate(entry)
        for entry in request_log_store.list_recent(limit)
    ]
    return RequestLogListResponse(total=request_log_store.count(), entries=entries)
