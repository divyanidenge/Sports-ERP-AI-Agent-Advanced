import sys
import os

sys.path.insert(0, os.path.abspath("."))
os.environ["DB_PATH"] = "sports_erp_test.db"

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import reset_db_for_tests, get_db_connection

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    reset_db_for_tests()
    yield

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def admin_token(client):
    resp = client.post("/auth/login", json={"email": "admin@sports.edu", "password": "admin123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]

@pytest.fixture
def student_token(client):
    resp = client.post("/auth/login", json={"email": "student@sports.edu", "password": "student123"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]
