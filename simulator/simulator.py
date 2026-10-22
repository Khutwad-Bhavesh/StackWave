#!/usr/bin/env python3
"""
RFID Edge Reader Simulator
Emulates physical RFID reader terminals (Checkout Kiosks, Return Chutes, Shelf Antennas, Exit Gates).
Signs all outgoing payloads with HMAC-SHA256, generates cryptographic nonces, and tests cloud ingestion.
"""

import sys
import time
import uuid
import hmac
import hashlib
import json
import argparse
import requests
from typing import Dict, Any, Optional

DEFAULT_API_URL = "http://localhost:8000"

# Reader Registry & Pre-Shared Secret Keys
READERS = {
    "1": {
        "id": "CHECKOUT-01",
        "name": "Self-Checkout Kiosk 1",
        "key": "checkout-secret-key-9988",
        "type": "CHECKOUT"
    },
    "2": {
        "id": "RETURN-01",
        "name": "Smart Return Drop Chute",
        "key": "return-secret-key-4455",
        "type": "RETURN"
    },
    "3": {
        "id": "SHELF-CS-01",
        "name": "Shelf Antenna - CS Stacks",
        "key": "shelf-secret-key-1122",
        "type": "SHELF"
    },
    "4": {
        "id": "GATE-01",
        "name": "Anti-Theft Exit Gate",
        "key": "gate-secret-key-7766",
        "type": "EXIT_GATE"
    }
}

SAMPLE_TAGS = {
    "1": ("CARD-ALICE-001", "Member Card - Alice Johnson (Clear)"),
    "2": ("CARD-BOB-002", "Member Card - Bob Smith (Has Overdue Book)"),
    "3": ("CARD-CHARLIE-003", "Member Card - Charlie Brown (Clear)"),
    "4": ("TAG-BK-CLEAN-01", "Book: Clean Code (Copy 1)"),
    "5": ("TAG-BK-CLEAN-02", "Book: Clean Code (Copy 2 - Available)"),
    "6": ("TAG-BK-DDIA-01", "Book: Designing Data-Intensive Apps (Copy 1)"),
    "7": ("TAG-BK-NET-01", "Book: Computer Networks (Copy 1 - Available)"),
    "8": ("TAG-BK-PRAG-01", "Book: The Pragmatic Programmer (Copy 1)"),
    "9": ("TAG-UNKNOWN-99", "Unregistered RFID Tag")
}

# ANSI colors
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BOLD = "\033[1m"
RESET = "\033[0m"


def compute_hmac_signature(reader_id: str, tag_uid: str, timestamp: int, nonce: str, secret_key: str) -> str:
    message = f"{reader_id}:{tag_uid}:{timestamp}:{nonce}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def send_scan(
    api_url: str,
    reader_id: str,
    secret_key: str,
    tag_uid: str,
    custom_timestamp: Optional[int] = None,
    custom_nonce: Optional[str] = None,
    custom_signature: Optional[str] = None
) -> Dict[str, Any]:
    timestamp = custom_timestamp if custom_timestamp is not None else int(time.time())
    nonce = custom_nonce if custom_nonce is not None else uuid.uuid4().hex
    signature = custom_signature if custom_signature is not None else compute_hmac_signature(reader_id, tag_uid, timestamp, nonce, secret_key)

    payload = {
        "reader_id": reader_id,
        "tag_uid": tag_uid,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": signature
    }

    t0 = time.time()
    try:
        response = requests.post(f"{api_url}/rfid/scan", json=payload, timeout=5)
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        return {
            "status_code": response.status_code,
            "latency_ms": elapsed_ms,
            "data": response.json(),
            "payload": payload
        }
    except Exception as e:
        return {
            "status_code": 0,
            "latency_ms": 0,
            "data": {"error": str(e)},
            "payload": payload
        }


def print_scan_result(result: Dict[str, Any]):
    code = result["status_code"]
    latency = result["latency_ms"]
    data = result["data"]
    payload = result["payload"]

    print(f"\n{BOLD}─── Scan Transmission ──────────────────────────────────────{RESET}")
    print(f"Reader:    {CYAN}{payload['reader_id']}{RESET}")
    print(f"Tag UID:   {MAGENTA}{payload['tag_uid']}{RESET}")
    print(f"Timestamp: {payload['timestamp']} | Nonce: {payload['nonce'][:12]}...")
    print(f"HMAC-SHA:  {payload['signature'][:32]}... ({BOLD}64 hex digits{RESET})")
    print(f"Network:   HTTP {code} ({latency}ms)")

    status = data.get("status", "unknown")
    res_code = data.get("result_code", "")
    msg = data.get("message", data.get("detail", str(data)))

    if code == 200:
        if status == "success":
            color = GREEN
            prefix = "✔ SUCCESS"
        elif status == "debounced":
            color = YELLOW
            prefix = "⚡ DEBOUNCED"
        elif status == "alert":
            color = RED
            prefix = "🚨 SECURITY ALARM"
        else:
            color = YELLOW
            prefix = "⚠ REJECTED"
        print(f"Result:    {color}{BOLD}{prefix} [{res_code}]{RESET} - {msg}")
    elif code == 401:
        print(f"Result:    {RED}{BOLD}✖ 401 UNAUTHORIZED / TAMPERED SIGNATURE{RESET} - {msg}")
    else:
        print(f"Result:    {RED}{BOLD}✖ ERROR {code}{RESET} - {msg}")
    print(f"{BOLD}────────────────────────────────────────────────────────────{RESET}\n")


def run_security_audit(api_url: str):
    print(f"\n{BOLD}{CYAN}=== Starting RFID Edge Security & Debounce Audit ==={RESET}\n")

    reader = READERS["1"]
    tag = "CARD-ALICE-001"

    # Test 1: Authentic Ingest
    print(f"{BOLD}[1/5] Testing Authentic Signed Scan...{RESET}")
    r1 = send_scan(api_url, reader["id"], reader["key"], tag)
    print_scan_result(r1)
    assert r1["status_code"] == 200 and r1["data"]["status"] == "success", "Authentic scan failed"
    print(f"{GREEN}✔ Passed Authentic Ingest Check{RESET}\n")

    # Test 2: Tampered HMAC Signature
    print(f"{BOLD}[2/5] Testing Tampered HMAC Signature Attack...{RESET}")
    fake_sig = "deadbeef" * 8
    r2 = send_scan(api_url, reader["id"], reader["key"], tag, custom_signature=fake_sig)
    print_scan_result(r2)
    assert r2["status_code"] == 401, "Server failed to reject tampered HMAC signature"
    print(f"{GREEN}✔ Passed Tampered HMAC Signature Defense{RESET}\n")

    # Test 3: Replay Attack (Re-transmitting exact payload)
    print(f"{BOLD}[3/5] Testing Replay Attack Defense (Re-sending same nonce)...{RESET}")
    time.sleep(2.1)
    ts = int(time.time())
    nonce = "replay-nonce-" + uuid.uuid4().hex[:8]
    sig = compute_hmac_signature(reader["id"], tag, ts, nonce, reader["key"])

    # Legitimate first transmission
    send_scan(api_url, reader["id"], reader["key"], tag, custom_timestamp=ts, custom_nonce=nonce, custom_signature=sig)
    # Replay malicious transmission
    r3 = send_scan(api_url, reader["id"], reader["key"], tag, custom_timestamp=ts, custom_nonce=nonce, custom_signature=sig)
    print_scan_result(r3)
    assert r3["data"].get("status") in ["rejected", "debounced"], "Replay attack was not blocked"
    print(f"{GREEN}✔ Passed Replay Attack Defense{RESET}\n")

    # Test 4: Clock Drift / Expired Timestamp
    print(f"{BOLD}[4/5] Testing Clock Drift (Timestamp 5 minutes in the past)...{RESET}")
    stale_ts = int(time.time()) - 300
    stale_nonce = uuid.uuid4().hex
    stale_sig = compute_hmac_signature(reader["id"], tag, stale_ts, stale_nonce, reader["key"])
    r4 = send_scan(api_url, reader["id"], reader["key"], tag, custom_timestamp=stale_ts, custom_nonce=stale_nonce, custom_signature=stale_sig)
    print_scan_result(r4)
    assert r4["data"].get("result_code") == "REPLAY_ATTACK", "Clock drift was not rejected"
    print(f"{GREEN}✔ Passed Clock Drift Freshness Check{RESET}\n")

    # Test 5: Hardware Burst Debounce Check
    print(f"{BOLD}[5/5] Testing 2.0s Duplicate Debounce Suppression...{RESET}")
    burst_tag = "TAG-BK-PRAG-01"
    # First burst read
    send_scan(api_url, reader["id"], reader["key"], burst_tag)
    # Rapid second read within 100ms
    r5 = send_scan(api_url, reader["id"], reader["key"], burst_tag)
    print_scan_result(r5)
    assert r5["data"].get("status") == "debounced", "Duplicate hardware read was not debounced"
    print(f"{GREEN}✔ Passed 2.0s Hardware Debounce Suppression{RESET}\n")

    print(f"{GREEN}{BOLD}=== All 5 Security & Debounce Tests Passed Successfully! ==={RESET}\n")


def run_scenario(api_url: str):
    print(f"\n{BOLD}{CYAN}=== Running Real-World Library Circulation Scenario ==={RESET}\n")

    checkout_reader = READERS["1"]
    return_reader = READERS["2"]
    shelf_reader = READERS["3"]
    gate_reader = READERS["4"]

    # Scenario 1: Patron with Overdue Book attempts checkout
    print(f"{YELLOW}▶ Step 1: Overdue Member Bob attempts checkout kiosk...{RESET}")
    r = send_scan(api_url, checkout_reader["id"], checkout_reader["key"], "CARD-BOB-002")
    print_scan_result(r)
    time.sleep(2.2)

    # Scenario 2: Patron Alice starts self-checkout session
    print(f"{CYAN}▶ Step 2: Member Alice taps card at checkout kiosk...{RESET}")
    r = send_scan(api_url, checkout_reader["id"], checkout_reader["key"], "CARD-ALICE-001")
    print_scan_result(r)
    time.sleep(2.2)

    # Scenario 3: Alice taps Clean Code Book Copy 2
    print(f"{CYAN}▶ Step 3: Alice taps 'Clean Code (Copy 2)' to checkout...{RESET}")
    r = send_scan(api_url, checkout_reader["id"], checkout_reader["key"], "TAG-BK-CLEAN-02")
    print_scan_result(r)
    time.sleep(2.2)

    # Scenario 4: Smart Return Chute
    print(f"{CYAN}▶ Step 4: Book returned in Smart Return Drop Chute...{RESET}")
    r = send_scan(api_url, return_reader["id"], return_reader["key"], "TAG-BK-CLEAN-02")
    print_scan_result(r)
    time.sleep(2.2)

    # Scenario 5: Shelf Inventory Sweep
    print(f"{CYAN}▶ Step 5: Shelf antenna reads 'The Pragmatic Programmer'...{RESET}")
    r = send_scan(api_url, shelf_reader["id"], shelf_reader["key"], "TAG-BK-PRAG-01")
    print_scan_result(r)
    time.sleep(2.2)

    # Scenario 6: Anti-Theft Exit Gate Breach
    print(f"{RED}▶ Step 6: Unchecked book 'Computer Networks' breaches Exit Gate...{RESET}")
    r = send_scan(api_url, gate_reader["id"], gate_reader["key"], "TAG-BK-NET-01")
    print_scan_result(r)

    print(f"{GREEN}{BOLD}=== Scenario Simulation Complete! ==={RESET}\n")


def run_interactive(api_url: str):
    print(f"\n{BOLD}{CYAN}=== Interactive RFID Edge Terminal Simulator ==={RESET}")
    print(f"Target Backend: {api_url}\n")

    current_reader_key = "1"

    while True:
        reader = READERS[current_reader_key]
        print(f"Active Reader Terminal: {CYAN}{BOLD}{reader['name']} [{reader['id']}]{RESET}")
        print("Choose an action:")
        print("  [1-4] Switch Reader (1: Checkout, 2: Return, 3: Shelf, 4: Exit Gate)")
        print("  [s]   Scan a sample Tag UID")
        print("  [c]   Custom Tag UID scan")
        print("  [d]   Test 2.0s Debounce Burst")
        print("  [r]   Test Replay Attack Defense")
        print("  [q]   Quit Simulator")

        choice = input("\nEnter choice: ").strip().lower()

        if choice in ["1", "2", "3", "4"]:
            current_reader_key = choice
            print(f"Switched to {READERS[current_reader_key]['name']}.\n")
        elif choice == "s":
            print("\nSelect Sample Tag to scan:")
            for k, (uid, desc) in SAMPLE_TAGS.items():
                print(f"  [{k}] {uid} - {desc}")
            tag_choice = input("Enter tag [1-9]: ").strip()
            if tag_choice in SAMPLE_TAGS:
                tag_uid = SAMPLE_TAGS[tag_choice][0]
                result = send_scan(api_url, reader["id"], reader["key"], tag_uid)
                print_scan_result(result)
            else:
                print("Invalid choice.\n")
        elif choice == "c":
            custom_uid = input("Enter Tag UID string: ").strip()
            if custom_uid:
                result = send_scan(api_url, reader["id"], reader["key"], custom_uid)
                print_scan_result(result)
        elif choice == "d":
            tag_uid = "TAG-BK-CLEAN-01"
            print("Sending 2 duplicate scans in 50ms...")
            send_scan(api_url, reader["id"], reader["key"], tag_uid)
            r2 = send_scan(api_url, reader["id"], reader["key"], tag_uid)
            print_scan_result(r2)
        elif choice == "r":
            tag_uid = "CARD-ALICE-001"
            ts = int(time.time())
            nonce = uuid.uuid4().hex
            sig = compute_hmac_signature(reader["id"], tag_uid, ts, nonce, reader["key"])
            print("Sending legitimate scan...")
            send_scan(api_url, reader["id"], reader["key"], tag_uid, ts, nonce, sig)
            print("Injecting replay scan with identical nonce...")
            r_rep = send_scan(api_url, reader["id"], reader["key"], tag_uid, ts, nonce, sig)
            print_scan_result(r_rep)
        elif choice == "q":
            print("Exiting simulator.")
            break
        else:
            print("Unrecognized option.\n")


def main():
    parser = argparse.ArgumentParser(description="RFID Edge Reader Simulator & Ingest Tester")
    parser.add_argument("--url", default=DEFAULT_API_URL, help=f"Cloud API Base URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--mode", choices=["interactive", "scenario", "security-audit"], default="interactive",
                        help="Operation mode: interactive, scenario, or security-audit")

    args = parser.parse_args()

    if args.mode == "security-audit":
        run_security_audit(args.url)
    elif args.mode == "scenario":
        run_scenario(args.url)
    else:
        run_interactive(args.url)


if __name__ == "__main__":
    main()
