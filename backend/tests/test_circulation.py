import time
import uuid
import datetime
from app.security import generate_hmac_signature

CHECKOUT_ID = "CHECKOUT-01"
CHECKOUT_KEY = "checkout-secret-key-9988"

RETURN_ID = "RETURN-01"
RETURN_KEY = "return-secret-key-4455"

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

def test_checkout_book_without_card_blocked(client):
    # Book tag tapped without prior member session
    resp = send_scan(client, CHECKOUT_ID, CHECKOUT_KEY, "TAG-BK-CLEAN-02")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["result_code"] == "NO_ACTIVE_SESSION"

def test_overdue_member_blocked_from_checkout(client):
    # Bob has an overdue loan seeded
    # We must sleep briefly to avoid debounce from previous runs if any
    time.sleep(2.1)
    resp = send_scan(client, CHECKOUT_ID, CHECKOUT_KEY, "CARD-BOB-002")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["result_code"] == "CHECKOUT_BLOCKED_OVERDUE"
    assert "overdue" in data["message"].lower()

def test_full_self_checkout_flow(client):
    time.sleep(2.1)
    # Step 1: Alice taps her card
    r1 = send_scan(client, CHECKOUT_ID, CHECKOUT_KEY, "CARD-ALICE-001")
    assert r1.status_code == 200
    assert r1.json()["status"] == "success"
    assert r1.json()["result_code"] == "SESSION_OPENED"

    time.sleep(2.1)
    # Step 2: Alice taps available book "Designing Data-Intensive Applications" Copy 2
    r2 = send_scan(client, CHECKOUT_ID, CHECKOUT_KEY, "TAG-BK-DDIA-02")
    assert r2.status_code == 200
    assert r2.json()["status"] == "success"
    assert r2.json()["result_code"] == "CHECKOUT_COMPLETE"
    assert "Checked out" in r2.json()["message"]

def test_return_flow_with_fine_calculation(client):
    time.sleep(2.1)
    # Return DDIA Copy 2 on the return chute
    r = send_scan(client, RETURN_ID, RETURN_KEY, "TAG-BK-DDIA-02")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["result_code"] == "RETURN_COMPLETE"
    assert data["details"]["fine_amount"] == 0.0

def test_loan_renewal_single_limit(client):
    # Alice's seeded active loan for "Clean Code"
    loans_resp = client.get("/loans?status=ACTIVE")
    assert loans_resp.status_code == 200
    loans = loans_resp.json()

    alice_loan = None
    for l in loans:
        if l["member_name"] == "Alice Johnson" and l["renewal_count"] == 0:
            alice_loan = l
            break

    assert alice_loan is not None
    loan_id = alice_loan["id"]

    # First renewal succeeds
    r1 = client.post(f"/loans/{loan_id}/renew")
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["success"] is True
    assert data1["renewal_count"] == 1

    # Second renewal must be blocked
    r2 = client.post(f"/loans/{loan_id}/renew")
    assert r2.status_code == 400
    assert "Maximum renewal limit" in r2.json()["detail"]

def test_overdue_loan_renewal_blocked(client):
    # Bob's loan is overdue
    loans_resp = client.get("/loans?overdue_only=true")
    assert loans_resp.status_code == 200
    overdue_loans = loans_resp.json()
    assert len(overdue_loans) > 0

    overdue_loan_id = overdue_loans[0]["id"]
    r = client.post(f"/loans/{overdue_loan_id}/renew")
    assert r.status_code == 400
    assert "Cannot renew an overdue book" in r.json()["detail"]
