import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Reader, BookCopy, Member, Loan, CheckoutSession, ScanEvent, Alert
from app.schemas import ScanIngestRequest, ScanIngestResponse
from app.security import verify_hmac_signature, check_replay_attack, check_rfid_debounce

router = APIRouter(prefix="/rfid", tags=["RFID Edge Ingestion & Processing"])

@router.post("/scan", response_model=ScanIngestResponse)
def ingest_rfid_scan(payload: ScanIngestRequest, db: Session = Depends(get_db)):
    """
    FR3 Ingest Endpoint:
    1. Authenticates reader device by ID.
    2. Cryptographically verifies HMAC-SHA256 signature using reader's shared secret.
    3. Blocks replay attacks via timestamp freshness window and nonce uniqueness.
    4. Debounces duplicate hardware reads within 2.0s window.
    5. Dispatches to circulation engine, tracking, or security theft alarm.
    """
    now = datetime.datetime.utcnow()

    # 1. Lookup Reader
    reader = db.query(Reader).filter(Reader.device_id == payload.reader_id).first()
    if not reader or not reader.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unauthorized or unregistered reader device: '{payload.reader_id}'"
        )

    # 2. Cryptographic HMAC Verification
    is_valid_sig = verify_hmac_signature(
        device_id=payload.reader_id,
        tag_uid=payload.tag_uid,
        timestamp=payload.timestamp,
        nonce=payload.nonce,
        provided_signature=payload.signature,
        secret_key=reader.secret_key
    )

    if not is_valid_sig:
        event = ScanEvent(
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            signature_valid=False,
            result_status="INVALID_SIGNATURE",
            action_detail="HMAC-SHA256 signature mismatch"
        )
        db.add(event)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tampered or invalid HMAC signature"
        )

    # 3. Guard against Replay Attacks
    is_fresh, replay_reason = check_replay_attack(
        device_id=payload.reader_id,
        timestamp=payload.timestamp,
        nonce=payload.nonce
    )
    if not is_fresh:
        event = ScanEvent(
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            signature_valid=True,
            result_status="REPLAY_BLOCKED",
            action_detail=f"Replay rejected: {replay_reason}"
        )
        db.add(event)
        db.commit()
        return ScanIngestResponse(
            status="rejected",
            result_code="REPLAY_ATTACK",
            message=replay_reason,
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid
        )

    # 4. Debounce duplicate burst reads
    is_duplicate = check_rfid_debounce(payload.reader_id, payload.tag_uid)
    if is_duplicate:
        event = ScanEvent(
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            signature_valid=True,
            result_status="DEBOUNCED",
            action_detail=f"Duplicate scan suppressed within {settings.RFID_DEBOUNCE_WINDOW_SECONDS}s window"
        )
        db.add(event)
        db.commit()
        return ScanIngestResponse(
            status="debounced",
            result_code="DEBOUNCED",
            message=f"Duplicate RFID scan ignored within {settings.RFID_DEBOUNCE_WINDOW_SECONDS}s",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid
        )

    # Update reader heartbeat and scan counter
    reader.last_heartbeat = now
    reader.total_scans += 1

    # 5. Route by Reader Role
    reader_type = reader.reader_type.upper()

    if reader_type == "CHECKOUT":
        return handle_checkout_scan(payload, reader, db, now)
    elif reader_type == "RETURN":
        return handle_return_scan(payload, reader, db, now)
    elif reader_type == "SHELF":
        return handle_shelf_scan(payload, reader, db, now)
    elif reader_type == "EXIT_GATE":
        return handle_exit_gate_scan(payload, reader, db, now)
    else:
        return ScanIngestResponse(
            status="rejected",
            result_code="UNKNOWN_READER_TYPE",
            message=f"Unsupported reader type: {reader.reader_type}",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid
        )


def handle_checkout_scan(payload: ScanIngestRequest, reader: Reader, db: Session, now: datetime.datetime) -> ScanIngestResponse:
    """Handles Self-Checkout: Member Card scan opens session, Book tag checkout adds loans."""
    # Check if scanned UID is a Member Card
    member = db.query(Member).filter(Member.member_card_uid == payload.tag_uid).first()
    if member:
        if not member.is_active:
            log_event(db, payload, "MEMBER_CARD", "MEMBER_INACTIVE", f"Member {member.name} is deactivated")
            return ScanIngestResponse(
                status="rejected",
                result_code="MEMBER_INACTIVE",
                message=f"Card rejected: Member '{member.name}' is deactivated. Contact librarian.",
                reader_id=payload.reader_id,
                tag_uid=payload.tag_uid,
                entity_type="MEMBER"
            )

        # Check for overdue books (FR4 requirement)
        active_loans = db.query(Loan).filter(Loan.member_id == member.id, Loan.status == "ACTIVE").all()
        overdue_loans = [l for l in active_loans if l.due_date < now]
        if overdue_loans:
            log_event(db, payload, "MEMBER_CARD", "CHECKOUT_BLOCKED_OVERDUE", f"Blocked: {len(overdue_loans)} overdue loans")
            return ScanIngestResponse(
                status="rejected",
                result_code="CHECKOUT_BLOCKED_OVERDUE",
                message=f"Self-checkout blocked: {member.name} has {len(overdue_loans)} overdue book(s). Return them before borrowing more.",
                reader_id=payload.reader_id,
                tag_uid=payload.tag_uid,
                entity_type="MEMBER",
                details={"overdue_count": len(overdue_loans)}
            )

        # Open / Refresh session
        existing_session = db.query(CheckoutSession).filter(
            CheckoutSession.reader_id == reader.device_id,
            CheckoutSession.status == "OPEN"
        ).first()

        if existing_session:
            if existing_session.member_id == member.id:
                existing_session.last_activity_at = now
                session = existing_session
            else:
                existing_session.status = "CANCELLED"
                session = CheckoutSession(
                    reader_id=reader.device_id,
                    member_id=member.id,
                    status="OPEN",
                    started_at=now,
                    last_activity_at=now,
                    scanned_copies_count=0
                )
                db.add(session)
        else:
            session = CheckoutSession(
                reader_id=reader.device_id,
                member_id=member.id,
                status="OPEN",
                started_at=now,
                last_activity_at=now,
                scanned_copies_count=0
            )
            db.add(session)

        db.commit()
        log_event(db, payload, "MEMBER_CARD", "SESSION_OPENED", f"Active session opened for {member.name}")

        available_quota = member.max_books - len(active_loans)
        return ScanIngestResponse(
            status="success",
            result_code="SESSION_OPENED",
            message=f"Welcome, {member.name}! Self-checkout active. Tap books to checkout (Quota remaining: {available_quota}/{member.max_books}).",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            entity_type="MEMBER",
            details={
                "member_name": member.name,
                "active_loans": len(active_loans),
                "max_books": member.max_books,
                "remaining_quota": available_quota
            }
        )

    # Scanned UID is not a member card, check if it's a Book Copy
    copy = db.query(BookCopy).filter(BookCopy.tag_uid == payload.tag_uid).first()
    if copy:
        # Check active session on this reader
        session = db.query(CheckoutSession).filter(
            CheckoutSession.reader_id == reader.device_id,
            CheckoutSession.status == "OPEN"
        ).first()

        if not session:
            log_event(db, payload, "BOOK_TAG", "NO_ACTIVE_SESSION", "Book tapped without active member card session")
            return ScanIngestResponse(
                status="rejected",
                result_code="NO_ACTIVE_SESSION",
                message="Please tap your Member Card on the reader first to start checkout.",
                reader_id=payload.reader_id,
                tag_uid=payload.tag_uid,
                entity_type="BOOK"
            )

        # Check session inactivity timeout
        inactivity_sec = (now - session.last_activity_at).total_seconds()
        if inactivity_sec > settings.SESSION_TIMEOUT_SECONDS:
            session.status = "TIMED_OUT"
            db.commit()
            log_event(db, payload, "BOOK_TAG", "SESSION_TIMED_OUT", "Session timed out due to inactivity")
            return ScanIngestResponse(
                status="rejected",
                result_code="SESSION_TIMED_OUT",
                message="Checkout session timed out. Please tap your Member Card again.",
                reader_id=payload.reader_id,
                tag_uid=payload.tag_uid,
                entity_type="BOOK"
            )

        # Check book availability
        if copy.status != "AVAILABLE":
            log_event(db, payload, "BOOK_TAG", "COPY_NOT_AVAILABLE", f"Copy status is {copy.status}")
            return ScanIngestResponse(
                status="rejected",
                result_code="COPY_NOT_AVAILABLE",
                message=f"'{copy.book.title}' is not available (Status: {copy.status}).",
                reader_id=payload.reader_id,
                tag_uid=payload.tag_uid,
                entity_type="BOOK"
            )

        # Check member loan limit (FR4: max 5 books)
        member = db.query(Member).filter(Member.id == session.member_id).first()
        active_loans_count = db.query(Loan).filter(Loan.member_id == member.id, Loan.status == "ACTIVE").count()

        if active_loans_count >= member.max_books:
            log_event(db, payload, "BOOK_TAG", "LIMIT_EXCEEDED", f"Member reached loan cap of {member.max_books}")
            return ScanIngestResponse(
                status="rejected",
                result_code="LIMIT_EXCEEDED",
                message=f"Limit exceeded: {member.name} already has {active_loans_count} books checked out (Cap: {member.max_books}).",
                reader_id=payload.reader_id,
                tag_uid=payload.tag_uid,
                entity_type="BOOK"
            )

        # Perform checkout
        due_date = now + datetime.timedelta(days=settings.DEFAULT_LOAN_DAYS)
        loan = Loan(
            copy_id=copy.id,
            member_id=member.id,
            checkout_at=now,
            due_date=due_date,
            status="ACTIVE",
            fine_amount=0.0,
            renewal_count=0
        )
        db.add(loan)

        copy.status = "CHECKED_OUT"
        copy.shelf_location = f"With Member ({member.name})"
        copy.last_seen_reader_id = reader.device_id
        copy.last_seen_at = now

        session.scanned_copies_count += 1
        session.last_activity_at = now

        db.commit()
        db.refresh(loan)

        log_event(db, payload, "BOOK_TAG", "SUCCESS_CHECKOUT", f"Checked out '{copy.book.title}' to {member.name}")
        return ScanIngestResponse(
            status="success",
            result_code="CHECKOUT_COMPLETE",
            message=f"Checked out '{copy.book.title}'. Due by {due_date.strftime('%Y-%m-%d')}.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            entity_type="BOOK",
            details={
                "book_title": copy.book.title,
                "due_date": due_date.isoformat(),
                "borrower": member.name,
                "session_items": session.scanned_copies_count
            }
        )

    # Scanned tag not recognized
    log_event(db, payload, "UNKNOWN", "UNRECOGNIZED_TAG", f"Unknown UID: {payload.tag_uid}")
    return ScanIngestResponse(
        status="rejected",
        result_code="UNRECOGNIZED_TAG",
        message=f"Unrecognized RFID tag: '{payload.tag_uid}'. Register card or book first.",
        reader_id=payload.reader_id,
        tag_uid=payload.tag_uid
    )


def handle_return_scan(payload: ScanIngestRequest, reader: Reader, db: Session, now: datetime.datetime) -> ScanIngestResponse:
    """Handles smart return chute scan with overdue fine calculation (FR5)."""
    copy = db.query(BookCopy).filter(BookCopy.tag_uid == payload.tag_uid).first()
    if not copy:
        log_event(db, payload, "UNKNOWN", "UNREGISTERED_COPY", "Return scan of unregistered tag")
        return ScanIngestResponse(
            status="rejected",
            result_code="UNREGISTERED_TAG",
            message=f"Tag '{payload.tag_uid}' does not match any registered book.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid
        )

    loan = db.query(Loan).filter(Loan.copy_id == copy.id, Loan.status == "ACTIVE").first()
    if not loan:
        copy.shelf_location = "Return Chute / Sorting Desk"
        copy.status = "AVAILABLE"
        copy.last_seen_reader_id = reader.device_id
        copy.last_seen_at = now
        db.commit()

        log_event(db, payload, "BOOK_TAG", "ALREADY_RETURNED", f"Copy '{copy.book.title}' already returned")
        return ScanIngestResponse(
            status="success",
            result_code="ALREADY_RETURNED",
            message=f"Book '{copy.book.title}' is already marked as returned. Placed in sorting queue.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            entity_type="BOOK"
        )

    # Calculate fine if overdue
    fine = 0.0
    overdue_days = 0
    if now > loan.due_date:
        overdue_sec = (now - loan.due_date).total_seconds()
        overdue_days = max(1, int(overdue_sec // 86400) + (1 if overdue_sec % 86400 > 0 else 0))
        fine = round(overdue_days * settings.FINE_PER_DAY, 2)

    loan.returned_at = now
    loan.status = "RETURNED"
    loan.fine_amount = fine

    copy.status = "AVAILABLE"
    copy.shelf_location = "Return Chute / Sorting Desk"
    copy.last_seen_reader_id = reader.device_id
    copy.last_seen_at = now

    db.commit()

    fine_msg = f" Late fine: ${fine:.2f} ({overdue_days} days overdue)." if fine > 0 else " No fine."
    log_event(db, payload, "BOOK_TAG", "SUCCESS_RETURN", f"Returned '{copy.book.title}'.{fine_msg}")

    return ScanIngestResponse(
        status="success",
        result_code="RETURN_COMPLETE",
        message=f"Book '{copy.book.title}' successfully returned.{fine_msg}",
        reader_id=payload.reader_id,
        tag_uid=payload.tag_uid,
        entity_type="BOOK",
        details={
            "book_title": copy.book.title,
            "borrower": loan.member.name,
            "overdue_days": overdue_days,
            "fine_amount": fine
        }
    )


def handle_shelf_scan(payload: ScanIngestRequest, reader: Reader, db: Session, now: datetime.datetime) -> ScanIngestResponse:
    """Handles shelf inventory sweep (FR7)."""
    copy = db.query(BookCopy).filter(BookCopy.tag_uid == payload.tag_uid).first()
    if not copy:
        log_event(db, payload, "UNKNOWN", "UNREGISTERED_SHELF_TAG", "Shelf reader detected unknown tag")
        return ScanIngestResponse(
            status="rejected",
            result_code="UNREGISTERED_TAG",
            message=f"Unknown tag '{payload.tag_uid}' detected on shelf.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid
        )

    # If book was marked CHECKED_OUT but found on shelf, someone returned it manually without kiosk scan
    if copy.status == "CHECKED_OUT":
        active_loan = db.query(Loan).filter(Loan.copy_id == copy.id, Loan.status == "ACTIVE").first()
        if active_loan:
            active_loan.returned_at = now
            active_loan.status = "RETURNED"
        copy.status = "AVAILABLE"

    copy.shelf_location = reader.location
    copy.last_seen_reader_id = reader.device_id
    copy.last_seen_at = now
    db.commit()

    log_event(db, payload, "BOOK_TAG", "SHELF_INVENTORY_UPDATE", f"Verified '{copy.book.title}' on {reader.location}")
    return ScanIngestResponse(
        status="success",
        result_code="SHELF_INVENTORY_UPDATE",
        message=f"Inventory verified: '{copy.book.title}' located on {reader.location}.",
        reader_id=payload.reader_id,
        tag_uid=payload.tag_uid,
        entity_type="BOOK",
        details={
            "book_title": copy.book.title,
            "location": reader.location
        }
    )


def handle_exit_gate_scan(payload: ScanIngestRequest, reader: Reader, db: Session, now: datetime.datetime) -> ScanIngestResponse:
    """Handles security gate scan: authorized exit or theft alert (FR7-8)."""
    copy = db.query(BookCopy).filter(BookCopy.tag_uid == payload.tag_uid).first()
    if not copy:
        # Unregistered tag passing through exit gate
        alert = Alert(
            alert_type="UNREGISTERED_TAG",
            severity="WARNING",
            reader_id=reader.device_id,
            tag_uid=payload.tag_uid,
            message=f"Security Notice: Unregistered RFID tag '{payload.tag_uid}' passed through Exit Gate."
        )
        db.add(alert)
        db.commit()

        log_event(db, payload, "UNKNOWN", "GATE_UNKNOWN_TAG", "Unregistered tag passing exit gate")
        return ScanIngestResponse(
            status="alert",
            result_code="SECURITY_WARNING",
            message=f"Warning: Unregistered tag '{payload.tag_uid}' detected at exit gate.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid
        )

    # Check if copy was legitimately checked out
    if copy.status == "CHECKED_OUT":
        copy.last_seen_reader_id = reader.device_id
        copy.last_seen_at = now
        db.commit()

        log_event(db, payload, "BOOK_TAG", "AUTHORIZED_EXIT", f"Authorized exit for '{copy.book.title}'")
        return ScanIngestResponse(
            status="success",
            result_code="AUTHORIZED_EXIT",
            message=f"Authorized Exit: '{copy.book.title}' is legitimately checked out.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            entity_type="BOOK",
            details={"book_title": copy.book.title}
        )
    else:
        # THEFT ALERT: Book is AVAILABLE, LOST, or REFERENCE, not checked out!
        alert = Alert(
            alert_type="UNAUTHORIZED_EXIT",
            severity="CRITICAL",
            reader_id=reader.device_id,
            copy_id=copy.id,
            tag_uid=payload.tag_uid,
            message=f"THEFT ALARM: Unchecked book '{copy.book.title}' (Tag: {payload.tag_uid}, Status: {copy.status}) breached Exit Gate!"
        )
        db.add(alert)
        copy.last_seen_reader_id = reader.device_id
        copy.last_seen_at = now
        db.commit()

        log_event(db, payload, "BOOK_TAG", "ALERT_THEFT", f"Theft alert triggered for '{copy.book.title}'")
        return ScanIngestResponse(
            status="alert",
            result_code="THEFT_ALARM",
            message=f"CRITICAL ALARM: Theft alert triggered for '{copy.book.title}'! Item was not checked out.",
            reader_id=payload.reader_id,
            tag_uid=payload.tag_uid,
            entity_type="BOOK",
            details={
                "book_title": copy.book.title,
                "current_status": copy.status,
                "location": reader.location
            }
        )


def log_event(db: Session, payload: ScanIngestRequest, tag_type: str, result_status: str, detail: str):
    event = ScanEvent(
        reader_id=payload.reader_id,
        tag_uid=payload.tag_uid,
        tag_type=tag_type,
        timestamp=payload.timestamp,
        nonce=payload.nonce,
        signature_valid=True,
        result_status=result_status,
        action_detail=detail
    )
    db.add(event)
    db.commit()


@router.post("/session/cancel")
def cancel_checkout_session(reader_id: str, db: Session = Depends(get_db)):
    """Ends or cancels an active self-checkout session."""
    session = db.query(CheckoutSession).filter(
        CheckoutSession.reader_id == reader_id,
        CheckoutSession.status == "OPEN"
    ).first()
    if not session:
        return {"status": "ok", "message": "No active session on this reader."}

    session.status = "COMPLETED"
    db.commit()
    return {"status": "ok", "message": f"Checkout session for member ID {session.member_id} closed."}
