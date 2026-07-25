from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

pytestmark = pytest.mark.integration


def _events():
    async def generate(_q, _thread_id):
        yield "thought", {"content": "Intent: Technical"}
        yield "token", {"content": "Answer [S1]"}
        yield "source", {"chunks": ["[S1] SOURCE: guide.md\nCONTENT: evidence"]}
        yield "done", {"sources_used": ["rag_documents"]}

    return generate


def test_query_collects_the_shared_stream_pipeline(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", None)
    with patch("app.main.query_events", _events()):
        response = TestClient(app).post("/query", json={"q": "question", "thread_id": "thread-1"})

    assert response.status_code == 200
    assert response.json() == {
        "question": "question",
        "answer": "Answer [S1]",
        "thought_process": ["Intent: Technical"],
        "status": "Response generated.",
        "sources": ["[S1] SOURCE: guide.md\nCONTENT: evidence"],
    }


def test_query_rejects_blank_question_and_invalid_thread_id(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", None)
    client = TestClient(app)

    assert client.post("/query", json={"q": "   ", "thread_id": "thread-1"}).status_code == 422
    assert client.post("/query", json={"q": "question", "thread_id": "bad thread id"}).status_code == 422


def test_delete_conversation_removes_redis_and_mem0_scope(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", None)
    with (
        patch("app.services.conversation_routes.delete_history") as delete_history,
        patch("app.services.conversation_routes.mem0_enabled", return_value=True),
        patch("app.services.conversation_routes.delete_memories") as delete_memories,
    ):
        response = TestClient(app).delete("/conversations/thread-1")

    assert response.status_code == 204
    delete_history.assert_called_once_with("thread-1")
    delete_memories.assert_called_once_with("thread-1")


def test_upload_rejects_invalid_pdf_signature(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", None)
    response = TestClient(app).post(
        "/ingest/document",
        files={"file": ("report.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is not a valid PDF."
