from fastapi.testclient import TestClient

from ops.backend import API_KEY, app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "MLOps Platform is running"}


def test_unauthorized_services():
    # 故意不带 X-Ops-Key，预期返回 401
    response = client.get("/v1/services")
    assert response.status_code == 401
    assert response.json()["status"] == "error"


def test_list_services_authorized():
    # 带上正确的 Key，预期返回 200
    headers = {"X-Ops-Key": API_KEY}
    response = client.get("/v1/services", headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["services"][0]["name"] == "medical-api"
