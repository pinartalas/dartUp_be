from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_logging import RequestLogStore, install_request_logging


def test_request_logging_records_recent_requests():
    store = RequestLogStore(max_entries=2)
    app = FastAPI()
    install_request_logging(app, store=store)

    @app.get("/ping/{item_id}")
    def ping(item_id: int):
        return {"item_id": item_id}

    client = TestClient(app)

    response = client.get("/ping/123?source=test", headers={"user-agent": "pytest"})

    assert response.status_code == 200
    entries = store.list_recent()
    assert len(entries) == 1
    assert entries[0].method == "GET"
    assert entries[0].path == "/ping/123"
    assert entries[0].query_string == "source=test"
    assert entries[0].route == "/ping/{item_id}"
    assert entries[0].status_code == 200
    assert entries[0].duration_ms >= 0
    assert entries[0].user_agent == "pytest"
