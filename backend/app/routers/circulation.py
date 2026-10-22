import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Loan, BookCopy, Member, User
from app.schemas import LoanResponse, RenewResponse
from app.security import get_current_user

router = APIRouter(prefix="/loans", tags=["Circulation & Loans"])

@router.get("", response_model=List[LoanResponse])
def list_loans(
    member_id: Optional[int] = None,
    status: Optional[str] = None,
    overdue_only: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(Loan)
    now = datetime.datetime.utcnow()

    if member_id:
        query = query.filter(Loan.member_id == member_id)
    if status:
        query = query.filter(Loan.status == status)
    if overdue_only:
        query = query.filter(Loan.status == "ACTIVE", Loan.due_date < now)

    loans = query.order_by(Loan.checkout_at.desc()).all()
    results = []
    for l in loans:
        resp = LoanResponse.model_validate(l)
        if l.copy and l.copy.book:
            resp.book_title = l.copy.book.title
            resp.tag_uid = l.copy.tag_uid
        if l.member:
            resp.member_name = l.member.name
        results.append(resp)
    return results

@router.get("/{loan_id}", response_model=LoanResponse)
def get_loan(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    resp = LoanResponse.model_validate(loan)
    if loan.copy and loan.copy.book:
        resp.book_title = loan.copy.book.title
        resp.tag_uid = loan.copy.tag_uid
    if loan.member:
        resp.member_name = loan.member.name
    return resp

@router.post("/{loan_id}/renew", response_model=RenewResponse)
def renew_loan(loan_id: int, db: Session = Depends(get_db)):
    """
    FR6 Renewal Rule:
    - Exactly one renewal allowed (adds 14 days to due_date).
    - Blocked if renewal_count >= 1.
    - Blocked if book is already overdue (must return to library).
    - Blocked if loan is not in ACTIVE status.
    """
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan record not found")

    if loan.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot renew loan with status '{loan.status}'. Only ACTIVE loans can be renewed."
        )

    now = datetime.datetime.utcnow()
    if now > loan.due_date:
        raise HTTPException(
            status_code=400,
            detail="Cannot renew an overdue book. Please return the book to the library desk and clear any late fines."
        )

    if loan.renewal_count >= settings.MAX_RENEWALS_PER_LOAN:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum renewal limit ({settings.MAX_RENEWALS_PER_LOAN}) reached for this loan."
        )

    # Apply renewal
    extension_days = settings.DEFAULT_LOAN_DAYS
    loan.due_date = loan.due_date + datetime.timedelta(days=extension_days)
    loan.renewal_count += 1
    db.commit()
    db.refresh(loan)

    return RenewResponse(
        success=True,
        message=f"Loan renewed successfully for {extension_days} days. New due date: {loan.due_date.strftime('%Y-%m-%d')}.",
        loan_id=loan.id,
        new_due_date=loan.due_date,
        renewal_count=loan.renewal_count
    )
