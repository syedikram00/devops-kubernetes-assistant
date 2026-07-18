from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_index_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_ask_endpoint_calls_ollama():
    mock_ollama_response = Mock()
    mock_ollama_response.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "This is a test answer",
        }
    }

    with patch("app.main.requests.post", return_value=mock_ollama_response):
        response = client.post("/ask", json={"prompt": "test question"})

    assert response.status_code == 200
    assert response.json()["answer"] == "This is a test answer"
