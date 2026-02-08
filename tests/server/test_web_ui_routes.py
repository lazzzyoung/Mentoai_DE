import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _load_app() -> TestClient:
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    module = importlib.import_module("server.app.main")
    return TestClient(module.app)


client = _load_app()


def test_root_page_serves_html_shell() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Mento AI</title>" in response.text
    assert "Find your perfect" in response.text


def test_htmx_action_returns_partial_html() -> None:
    response = client.post("/api/action")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Action Successful!" in response.text


def test_legacy_root_health_response_for_json_clients() -> None:
    response = client.get("/", headers={"accept": "application/json"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"


def test_health_endpoint_is_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
