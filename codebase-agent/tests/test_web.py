from fastapi.testclient import TestClient
from web.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_repos_empty():
    resp = client.get("/repos")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)