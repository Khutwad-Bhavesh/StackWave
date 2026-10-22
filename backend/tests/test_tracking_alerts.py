import time
import uuid
from app.security import generate_hmac_signature

GATE_ID = "GATE-01"
GATE_KEY = "gate-secret-key-7766"

SHELF_ID = "SHELF-CS-01"
SHELF_KEY = "shelf-secret-key-1122"

def send_scan(client, reader_id, key, tag_uid):
    ts = int(time.time())
    nonce = uuid.uuid4().hex
    sig = generate_hmac_signature(reader_id, tag_uid, ts, nonce, key)
    return client.post("/rfid/scan", json={
        "reader_id": reader_id,
        "tag_uid": tag_uid,
        "timestamp": ts,
        "nonce": nonce,
        "signature": sig
    })

def test_shelf_inventory_sweep(client):
    time.sleep(2.1)
    # Scan Pragmatic Programmer on shelf
    resp = send_scan(client, SHELF_ID, SHELF_KEY, "TAG-BK-PRAG-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["result_code"] == "SHELF_INVENTORY_UPDATE"

    # Check tracking API
    t_resp = client.get("/tracking")
    assert t_resp.status_code == 200
    items = t_resp.json()
    prag = next(item for item in items if item["tag_uid"] == "TAG-BK-PRAG-01")
    assert prag["last_seen_reader_id"] == SHELF_ID

def test_exit_gate_theft_alarm(client):
    time.sleep(2.1)
    # Attempt to walk out with "Computer Networks" which is AVAILABLE (not checked out!)
    resp = send_scan(client, GATE_ID, GATE_KEY, "TAG-BK-NET-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alert"
    assert data["result_code"] == "THEFT_ALARM"

    # Check alerts endpoint
    alerts_resp = client.get("/alerts?unresolved_only=true")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    theft_alert = next(a for a in alerts if a["tag_uid"] == "TAG-BK-NET-01")
    assert theft_alert["severity"] == "CRITICAL"
    assert theft_alert["resolved"] is False

    # Resolve alert
    res_resp = client.post(f"/alerts/{theft_alert['id']}/resolve", json={"resolved_by": "guard_station_1"})
    assert res_resp.status_code == 200
    assert res_resp.json()["resolved"] is True
    assert res_resp.json()["resolved_by"] == "guard_station_1"

def test_exit_gate_authorized_exit(client):
    time.sleep(2.1)
    # Alice's book "Clean Code" Copy 1 is CHECKED_OUT
    resp = send_scan(client, GATE_ID, GATE_KEY, "TAG-BK-CLEAN-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["result_code"] == "AUTHORIZED_EXIT"
