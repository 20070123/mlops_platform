from fastapi.testclient import TestClient
from doctor.doctor_backend import app, API_KEY

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Doctor Backend is running"}

def test_unauthorized_models():
    # 故意不带 X-Doctor-Key，预期返回 401
    response = client.get("/v1/models")
    assert response.status_code == 401

def test_list_models_authorized():
    headers = {"X-Doctor-Key": API_KEY}
    response = client.get("/v1/models", headers=headers)
    assert response.status_code == 200
    assert "medical-api" in response.json()["models"]