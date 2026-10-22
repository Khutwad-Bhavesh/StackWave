from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import datetime

from app.database import get_db
from app.models import Book, BookCopy, Member, Reader, User, Loan
from app.schemas import (
    BookCreate, BookResponse,
    BookCopyCreate, BookCopyResponse,
    MemberCreate, MemberResponse,
    ReaderCreate, ReaderResponse
)
from app.security import require_roles, get_current_user

router = APIRouter(tags=["Catalog, Members & Readers"])

# ----------------- Books -----------------
@router.post("/books", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(
    book_in: BookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "librarian"]))
):
    book = Book(
        title=book_in.title,
        author=book_in.author,
        isbn=book_in.isbn,
        category=book_in.category,
        description=book_in.description
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book

@router.get("/books", response_model=List[BookResponse])
def list_books(
    search: Optional[str] = Query(None, description="Search by title, author, or ISBN"),
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Book)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_filter)) |
            (Book.author.ilike(search_filter)) |
            (Book.isbn.ilike(search_filter))
        )
    if category:
        query = query.filter(Book.category == category)
    return query.all()

@router.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book

# ----------------- Book Copies (RFID tagged items) -----------------
@router.post("/copies", response_model=BookCopyResponse, status_code=status.HTTP_201_CREATED)
def create_book_copy(
    copy_in: BookCopyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "librarian"]))
):
    # Check if book exists
    book = db.query(Book).filter(Book.id == copy_in.book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Referenced Book ID does not exist")

    # Check tag uniqueness
    existing_copy = db.query(BookCopy).filter(BookCopy.tag_uid == copy_in.tag_uid).first()
    if existing_copy:
        raise HTTPException(status_code=400, detail="RFID Tag UID already assigned to another book copy")

    # Ensure RFID tag does not collide with member cards
    existing_card = db.query(Member).filter(Member.member_card_uid == copy_in.tag_uid).first()
    if existing_card:
        raise HTTPException(status_code=400, detail="RFID Tag UID is already used as a Member Card UID")

    copy = BookCopy(
        book_id=copy_in.book_id,
        tag_uid=copy_in.tag_uid,
        shelf_location=copy_in.shelf_location,
        status="AVAILABLE"
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy

@router.get("/copies", response_model=List[BookCopyResponse])
def list_book_copies(
    tag_uid: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(BookCopy)
    if tag_uid:
        query = query.filter(BookCopy.tag_uid == tag_uid)
    if status:
        query = query.filter(BookCopy.status == status)
    return query.all()

# ----------------- Members -----------------
@router.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(
    member_in: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "librarian"]))
):
    existing_card = db.query(Member).filter(Member.member_card_uid == member_in.member_card_uid).first()
    if existing_card:
        raise HTTPException(status_code=400, detail="Member RFID Card UID already registered")

    existing_copy = db.query(BookCopy).filter(BookCopy.tag_uid == member_in.member_card_uid).first()
    if existing_copy:
        raise HTTPException(status_code=400, detail="RFID UID is already assigned to a Book Copy")

    member = Member(
        name=member_in.name,
        email=member_in.email,
        member_card_uid=member_in.member_card_uid,
        user_id=member_in.user_id,
        max_books=member_in.max_books,
        is_active=True
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    resp = MemberResponse.model_validate(member)
    resp.active_loans_count = 0
    resp.has_overdue = False
    return resp

@router.get("/members", response_model=List[MemberResponse])
def list_members(db: Session = Depends(get_db)):
    members = db.query(Member).all()
    now = datetime.datetime.utcnow()
    results = []
    for m in members:
        resp = MemberResponse.model_validate(m)
        active_loans = db.query(Loan).filter(Loan.member_id == m.id, Loan.status == "ACTIVE").all()
        resp.active_loans_count = len(active_loans)
        resp.has_overdue = any(loan.due_date < now for loan in active_loans)
        results.append(resp)
    return results

@router.get("/members/{member_id}", response_model=MemberResponse)
def get_member(member_id: int, db: Session = Depends(get_db)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    resp = MemberResponse.model_validate(member)
    now = datetime.datetime.utcnow()
    active_loans = db.query(Loan).filter(Loan.member_id == member.id, Loan.status == "ACTIVE").all()
    resp.active_loans_count = len(active_loans)
    resp.has_overdue = any(loan.due_date < now for loan in active_loans)
    return resp

# ----------------- Readers -----------------
@router.post("/readers", response_model=ReaderResponse, status_code=status.HTTP_201_CREATED)
def register_reader(
    reader_in: ReaderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    existing = db.query(Reader).filter(Reader.device_id == reader_in.device_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Reader device_id already registered")

    valid_types = ["CHECKOUT", "RETURN", "SHELF", "EXIT_GATE"]
    if reader_in.reader_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid reader_type. Must be one of {valid_types}")

    reader = Reader(
        device_id=reader_in.device_id,
        name=reader_in.name,
        reader_type=reader_in.reader_type,
        secret_key=reader_in.secret_key,
        location=reader_in.location,
        is_active=True,
        last_heartbeat=datetime.datetime.utcnow()
    )
    db.add(reader)
    db.commit()
    db.refresh(reader)
    return reader

@router.get("/readers", response_model=List[ReaderResponse])
def list_readers(db: Session = Depends(get_db)):
    return db.query(Reader).all()
