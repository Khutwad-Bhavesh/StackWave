def test_login_success(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "admin"
    assert data["username"] == "admin"

def test_login_invalid_password(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401
    assert "detail" in response.json()

def test_get_current_user_profile(client):
    login_resp = client.post("/auth/login", json={"username": "librarian", "password": "lib123"})
    token = login_resp.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "librarian"
    assert data["role"] == "librarian"

def test_rbac_admin_route_blocked_for_member(client):
    login_resp = client.post("/auth/login", json={"username": "member_alice", "password": "alice123"})
    token = login_resp.json()["access_token"]

    # Register reader requires admin role
    response = client.post(
        "/readers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "device_id": "TEST-READER-01",
            "name": "Test Reader",
            "reader_type": "CHECKOUT",
            "secret_key": "some-secret",
            "location": "Room 101"
        }
    )
    assert response.status_code == 403
