import time
import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.config import settings
from app.database import get_db
from app.models import Book, BookCopy, Member, Reader, Loan, CheckoutSession, ScanEvent, Alert
from app.schemas import HealthResponse, StatsResponse

router = APIRouter(tags=["Monitoring, Health & KPIs"])

START_TIME = time.time()

@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """
    FR11 Healthcheck: verifies DB readiness, uptime, and session count.
    Used by Nginx / AWS ALB / Kubernetes liveness & readiness probes.
    """
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    active_sessions = db.query(CheckoutSession).filter(CheckoutSession.status == "OPEN").count()
    uptime = time.time() - START_TIME

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database=db_status,
        active_sessions=active_sessions,
        timestamp=datetime.datetime.utcnow(),
        uptime_seconds=round(uptime, 2)
    )

@router.get("/metrics")
def prometheus_metrics(db: Session = Depends(get_db)):
    """
    FR11 Metrics: Prometheus exposition format for CloudWatch / Grafana scraping.
    """
    now = datetime.datetime.utcnow()
    total_books = db.query(Book).count()
    total_copies = db.query(BookCopy).count()
    copies_checked_out = db.query(BookCopy).filter(BookCopy.status == "CHECKED_OUT").count()
    active_loans = db.query(Loan).filter(Loan.status == "ACTIVE").count()
    overdue_loans = db.query(Loan).filter(Loan.status == "ACTIVE", Loan.due_date < now).count()
    unresolved_alerts = db.query(Alert).filter(Alert.resolved == False).count()
    active_sessions = db.query(CheckoutSession).filter(CheckoutSession.status == "OPEN").count()
    total_scans = db.query(func.sum(Reader.total_scans)).scalar() or 0
    uptime = time.time() - START_TIME

    lines = [
        "# HELP rfid_uptime_seconds Application uptime in seconds",
        "# TYPE rfid_uptime_seconds gauge",
        f"rfid_uptime_seconds {uptime:.2f}",
        "",
        "# HELP rfid_books_total Total number of registered book titles",
        "# TYPE rfid_books_total gauge",
        f"rfid_books_total {total_books}",
        "",
        "# HELP rfid_copies_total Total number of physical RFID-tagged copies",
        "# TYPE rfid_copies_total gauge",
        f"rfid_copies_total {total_copies}",
        "",
        "# HELP rfid_copies_checked_out Total number of copies currently checked out",
        "# TYPE rfid_copies_checked_out gauge",
        f"rfid_copies_checked_out {copies_checked_out}",
        "",
        "# HELP rfid_loans_active Total number of active member loans",
        "# TYPE rfid_loans_active gauge",
        f"rfid_loans_active {active_loans}",
        "",
        "# HELP rfid_loans_overdue Total number of loans past due date",
        "# TYPE rfid_loans_overdue gauge",
        f"rfid_loans_overdue {overdue_loans}",
        "",
        "# HELP rfid_alerts_unresolved Total number of unresolved security alarms",
        "# TYPE rfid_alerts_unresolved gauge",
        f"rfid_alerts_unresolved {unresolved_alerts}",
        "",
        "# HELP rfid_checkout_sessions_active Total open self-checkout sessions",
        "# TYPE rfid_checkout_sessions_active gauge",
        f"rfid_checkout_sessions_active {active_sessions}",
        "",
        "# HELP rfid_edge_scans_total Total scans ingested across all readers",
        "# TYPE rfid_edge_scans_total counter",
        f"rfid_edge_scans_total {total_scans}",
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

@router.get("/stats", response_model=StatsResponse)
def get_kpi_stats(db: Session = Depends(get_db)):
    """
    FR10 Dashboard KPIs: live aggregates, counts, overdue, and reader fleet status.
    """
    now = datetime.datetime.utcnow()
    total_books = db.query(Book).count()
    total_copies = db.query(BookCopy).count()
    copies_checked_out = db.query(BookCopy).filter(BookCopy.status == "CHECKED_OUT").count()
    copies_available = db.query(BookCopy).filter(BookCopy.status == "AVAILABLE").count()
    total_members = db.query(Member).count()
    active_loans = db.query(Loan).filter(Loan.status == "ACTIVE").count()
    overdue_loans = db.query(Loan).filter(Loan.status == "ACTIVE", Loan.due_date < now).count()
    unresolved_alerts = db.query(Alert).filter(Alert.resolved == False).count()

    today_start = datetime.datetime.combine(now.date(), datetime.time.min)
    total_scans_today = db.query(ScanEvent).filter(ScanEvent.created_at >= today_start).count()

    readers = db.query(Reader).all()
    fleet = []
    for r in readers:
        is_online = False
        if r.last_heartbeat:
            elapsed = (now - r.last_heartbeat).total_seconds()
            is_online = elapsed < 300  # 5 minutes
        fleet.append({
            "id": r.id,
            "device_id": r.device_id,
            "name": r.name,
            "type": r.reader_type,
            "location": r.location,
            "is_active": r.is_active,
            "is_online": is_online,
            "total_scans": r.total_scans,
            "last_heartbeat": r.last_heartbeat.isoformat() if r.last_heartbeat else None
        })

    return StatsResponse(
        total_books=total_books,
        total_copies=total_copies,
        copies_available=copies_available,
        copies_checked_out=copies_checked_out,
        total_members=total_members,
        active_loans=active_loans,
        overdue_loans=overdue_loans,
        unresolved_alerts=unresolved_alerts,
        total_scans_today=total_scans_today,
        reader_fleet=fleet
    )

@router.get("/events")
def get_recent_events(
    limit: int = Query(30, ge=1, le=100),
    reader_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    FR10 Live Feed: returns recent scan events for real-time dashboard visualization.
    """
    query = db.query(ScanEvent)
    if reader_id:
        query = query.filter(ScanEvent.reader_id == reader_id)
    if status:
        query = query.filter(ScanEvent.result_status == status)

    events = query.order_by(ScanEvent.created_at.desc()).limit(limit).all()
    results = []
    for e in events:
        results.append({
            "id": e.id,
            "reader_id": e.reader_id,
            "tag_uid": e.tag_uid,
            "tag_type": e.tag_type,
            "timestamp": e.timestamp,
            "nonce": e.nonce,
            "signature_valid": e.signature_valid,
            "result_status": e.result_status,
            "action_detail": e.action_detail,
            "created_at": e.created_at.isoformat()
        })
    return results
