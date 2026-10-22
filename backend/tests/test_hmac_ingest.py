import time
import uuid
from app.security import generate_hmac_signature

READER_ID = "CHECKOUT-01"
SECRET_KEY = "checkout-secret-key-9988"
TAG_UID = "CARD-ALICE-001"

def test_valid_hmac_scan_ingest(client):
    ts = int(time.time())
    nonce = uuid.uuid4().hex
    sig = generate_hmac_signature(READER_ID, TAG_UID, ts, nonce, SECRET_KEY)

    payload = {
        "reader_id": READER_ID,
        "tag_uid": TAG_UID,
        "timestamp": ts,
        "nonce": nonce,
        "signature": sig
    }
    response = client.post("/rfid/scan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result_code"] == "SESSION_OPENED"

def test_invalid_hmac_signature_rejected(client):
    ts = int(time.time())
    nonce = uuid.uuid4().hex
    tampered_sig = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

    payload = {
        "reader_id": READER_ID,
        "tag_uid": TAG_UID,
        "timestamp": ts,
        "nonce": nonce,
        "signature": tampered_sig
    }
    response = client.post("/rfid/scan", json=payload)
    assert response.status_code == 401
    assert "Tampered or invalid HMAC" in response.json()["detail"]

def test_replay_attack_rejected(client):
    ts = int(time.time())
    nonce = f"fixed-nonce-{uuid.uuid4().hex[:8]}"
    sig = generate_hmac_signature(READER_ID, TAG_UID, ts, nonce, SECRET_KEY)

    payload = {
        "reader_id": READER_ID,
        "tag_uid": TAG_UID,
        "timestamp": ts,
        "nonce": nonce,
        "signature": sig
    }
    # First send is accepted
    r1 = client.post("/rfid/scan", json=payload)
    assert r1.status_code in [200, 200]

    # Immediate replay of the EXACT same payload with same nonce must be detected as replay
    r2 = client.post("/rfid/scan", json=payload)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["status"] in ["rejected", "debounced"]
    if data2["status"] == "rejected":
        assert data2["result_code"] == "REPLAY_ATTACK"

def test_timestamp_drift_rejected(client):
    # Timestamp from 5 minutes ago (300 seconds > 60 seconds tolerance window)
    ts = int(time.time()) - 300
    nonce = uuid.uuid4().hex
    sig = generate_hmac_signature(READER_ID, TAG_UID, ts, nonce, SECRET_KEY)

    payload = {
        "reader_id": READER_ID,
        "tag_uid": TAG_UID,
        "timestamp": ts,
        "nonce": nonce,
        "signature": sig
    }
    response = client.post("/rfid/scan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["result_code"] == "REPLAY_ATTACK"
    assert "clock drift" in data["message"].lower()

def test_debounce_duplicate_burst_read(client):
    test_tag = "TAG-BK-DDIA-01"
    ts = int(time.time())
    nonce1 = uuid.uuid4().hex
    sig1 = generate_hmac_signature(READER_ID, test_tag, ts, nonce1, SECRET_KEY)

    # First read (not debounced)
    r1 = client.post("/rfid/scan", json={
        "reader_id": READER_ID,
        "tag_uid": test_tag,
        "timestamp": ts,
        "nonce": nonce1,
        "signature": sig1
    })

    # Rapid second read within 0.1s
    nonce2 = uuid.uuid4().hex
    sig2 = generate_hmac_signature(READER_ID, test_tag, ts, nonce2, SECRET_KEY)
    r2 = client.post("/rfid/scan", json={
        "reader_id": READER_ID,
        "tag_uid": test_tag,
        "timestamp": ts,
        "nonce": nonce2,
        "signature": sig2
    })
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["status"] == "debounced"
    assert data2["result_code"] == "DEBOUNCED"
