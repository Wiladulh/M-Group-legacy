from fastapi.testclient import TestClient
from app.main import create_app
def test_health():
    r=TestClient(create_app()).get("/api/v1/health"); assert r.status_code==200; assert r.json()["status"]=="ok"
def test_system():
    assert TestClient(create_app()).get("/api/v1/system").status_code==200
