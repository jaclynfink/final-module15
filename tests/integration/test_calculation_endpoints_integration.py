import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

from app.database import Base, get_db
from main import app


def _register_and_get_auth_headers(client: TestClient) -> dict[str, str]:
    suffix = uuid4().hex[:8]
    payload = {
        "username": f"calc_user_{suffix}",
        "email": f"calc_user_{suffix}@example.com",
        "password": "ValidPassword123",
    }
    response = client.post("/register", json=payload)
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.integration
def test_add_and_browse_calculations(client):
    headers = _register_and_get_auth_headers(client)

    create_response = client.post(
        "/calculations",
        json={"a": 10, "b": 2, "type": "Divide"},
        headers=headers,
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["a"] == 10
    assert created["b"] == 2
    assert created["type"] == "Divide"
    assert created["result"] == 5

    browse_response = client.get("/calculations", headers=headers)
    assert browse_response.status_code == 200
    items = browse_response.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]


@pytest.mark.integration
def test_read_calculation_by_id(client):
    headers = _register_and_get_auth_headers(client)

    create_response = client.post(
        "/calculations",
        json={"a": 7, "b": 8, "type": "Add"},
        headers=headers,
    )
    calculation_id = create_response.json()["id"]

    read_response = client.get(f"/calculations/{calculation_id}", headers=headers)

    assert read_response.status_code == 200
    payload = read_response.json()
    assert payload["id"] == calculation_id
    assert payload["result"] == 15


@pytest.mark.integration
def test_edit_calculation_with_put(client):
    headers = _register_and_get_auth_headers(client)

    create_response = client.post(
        "/calculations",
        json={"a": 9, "b": 3, "type": "Sub"},
        headers=headers,
    )
    calculation_id = create_response.json()["id"]

    update_response = client.put(
        f"/calculations/{calculation_id}",
        json={"a": 9, "b": 3, "type": "Multiply"},
        headers=headers,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["id"] == calculation_id
    assert updated["type"] == "Multiply"
    assert updated["result"] == 27


@pytest.mark.integration
def test_delete_calculation(client):
    headers = _register_and_get_auth_headers(client)

    create_response = client.post(
        "/calculations",
        json={"a": 20, "b": 5, "type": "Divide"},
        headers=headers,
    )
    calculation_id = create_response.json()["id"]

    delete_response = client.delete(f"/calculations/{calculation_id}", headers=headers)
    assert delete_response.status_code == 204

    read_response = client.get(f"/calculations/{calculation_id}", headers=headers)
    assert read_response.status_code == 404
    assert read_response.json()["error"] == "Calculation not found."


@pytest.mark.integration
def test_patch_calculation_with_partial_payload(client):
    headers = _register_and_get_auth_headers(client)

    create_response = client.post(
        "/calculations",
        json={"a": 20, "b": 5, "type": "Divide"},
        headers=headers,
    )
    calculation_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/calculations/{calculation_id}",
        json={"b": 4},
        headers=headers,
    )

    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["a"] == 20
    assert patched["b"] == 4
    assert patched["type"] == "Divide"
    assert patched["result"] is None


@pytest.mark.integration
def test_browse_returns_only_current_user_calculations(client):
    user_1_headers = _register_and_get_auth_headers(client)
    user_2_headers = _register_and_get_auth_headers(client)

    response_1 = client.post(
        "/calculations",
        json={"a": 1, "b": 2, "type": "Add"},
        headers=user_1_headers,
    )
    response_2 = client.post(
        "/calculations",
        json={"a": 3, "b": 4, "type": "Multiply"},
        headers=user_2_headers,
    )

    id_1 = response_1.json()["id"]
    id_2 = response_2.json()["id"]

    browse_user_1 = client.get("/calculations", headers=user_1_headers)
    assert browse_user_1.status_code == 200
    ids_user_1 = {item["id"] for item in browse_user_1.json()}
    assert id_1 in ids_user_1
    assert id_2 not in ids_user_1
