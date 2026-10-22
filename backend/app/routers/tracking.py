import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BookCopy, Alert, Loan, User
from app.schemas import TrackingItemResponse, AlertResponse, AlertResolveRequest
from app.security import require_roles

router = APIRouter(tags=["Tracking & Security Alerts"])

@router.get("/tracking", response_model=List[TrackingItemResponse])
def get_inventory_tracking(
    status: Optional[str] = None,
    shelf: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    FR7: Real-time location and status tracking for all physical RFID-tagged book copies.
    """
    query = db.query(BookCopy)
    if status:
        query = query.filter(BookCopy.status == status)
    if shelf:
        query = query.filter(BookCopy.shelf_location.ilike(f"%{shelf}%"))

    copies = query.all()
    results = []
    for c in copies:
        borrower_name = None
        if c.status == "CHECKED_OUT":
            active_loan = db.query(Loan).filter(Loan.copy_id == c.id, Loan.status == "ACTIVE").first()
            if active_loan and active_loan.member:
                borrower_name = active_loan.member.name

        results.append(
            TrackingItemResponse(
                copy_id=c.id,
                book_title=c.book.title if c.book else "Unknown Title",
                author=c.book.author if c.book else "Unknown Author",
                tag_uid=c.tag_uid,
                status=c.status,
                shelf_location=c.shelf_location,
                last_seen_reader_id=c.last_seen_reader_id,
                last_seen_at=c.last_seen_at,
                current_borrower=borrower_name
            )
        )
    return results

@router.get("/alerts", response_model=List[AlertResponse])
def get_security_alerts(
    unresolved_only: bool = True,
    severity: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    FR8: Retrieve security alerts such as Exit-Gate theft breaches, overdue tags, or unregistered UIDs.
    """
    query = db.query(Alert)
    if unresolved_only:
        query = query.filter(Alert.resolved == False)
    if severity:
        query = query.filter(Alert.severity == severity)

    return query.order_by(Alert.created_at.desc()).all()

@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_security_alert(
    alert_id: int,
    req: AlertResolveRequest,
    db: Session = Depends(get_db)
):
    """
    Mark an active security alert as acknowledged and resolved.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.resolved = True
    alert.resolved_by = req.resolved_by or "librarian"
    alert.resolved_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert
