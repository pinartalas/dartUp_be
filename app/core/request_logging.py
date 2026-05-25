import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from threading import Lock
from time import perf_counter
from typing import Optional

from fastapi import FastAPI, Request

logger = logging.getLogger("app.requests")


@dataclass(frozen=True)
class RecordedRequest:
    requested_at: datetime
    method: str
    path: str
    query_string: Optional[str]
    route: Optional[str]
    status_code: int
    duration_ms: float
    client_host: Optional[str]
    user_agent: Optional[str]


class RequestLogStore:
    def __init__(self, max_entries: int = 500):
        self._entries: deque[RecordedRequest] = deque(maxlen=max_entries)
        self._lock = Lock()

    def record(self, entry: RecordedRequest) -> None:
        with self._lock:
            self._entries.appendleft(entry)

    def list_recent(self, limit: int = 50) -> list[RecordedRequest]:
        with self._lock:
            return list(islice(self._entries, limit))

    def count(self) -> int:
        with self._lock:
            return len(self._entries)


request_log_store = RequestLogStore()


def install_request_logging(
    app: FastAPI,
    store: RequestLogStore = request_log_store,
) -> None:
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        requested_at = datetime.now(timezone.utc)
        started_at = perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            route = request.scope.get("route")
            route_path = getattr(route, "path", None) if route is not None else None
            query_string = request.url.query or None

            entry = RecordedRequest(
                requested_at=requested_at,
                method=request.method,
                path=request.url.path,
                query_string=query_string,
                route=route_path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_host=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            store.record(entry)
            logger.info(
                "%s %s -> %s %.2fms",
                entry.method,
                entry.path,
                entry.status_code,
                entry.duration_ms,
            )
