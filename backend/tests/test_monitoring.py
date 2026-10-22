def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "uptime_seconds" in data

def test_prometheus_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    content = response.text
    assert "rfid_uptime_seconds" in content
    assert "rfid_books_total" in content
    assert "rfid_copies_total" in content
    assert "rfid_loans_active" in content

def test_kpi_stats(client):
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_books"] > 0
    assert data["total_copies"] > 0
    assert data["total_members"] > 0
    assert len(data["reader_fleet"]) == 4

def test_events_feed(client):
    response = client.get("/events?limit=10")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
