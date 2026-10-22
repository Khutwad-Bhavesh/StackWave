import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), default="member", nullable=False)  # admin, librarian, member
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    member = relationship("Member", back_populates="user", uselist=False)

class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    member_card_uid = Column(String(64), unique=True, index=True, nullable=False)  # RFID Tag UID on card
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    max_books = Column(Integer, default=5, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="member")
    loans = relationship("Loan", back_populates="member")
    sessions = relationship("CheckoutSession", back_populates="member")

class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True, nullable=False)
    author = Column(String(255), nullable=False)
    isbn = Column(String(50), index=True, nullable=False)
    category = Column(String(100), default="General", nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    copies = relationship("BookCopy", back_populates="book", cascade="all, delete-orphan")

class BookCopy(Base):
    __tablename__ = "book_copies"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    tag_uid = Column(String(64), unique=True, index=True, nullable=False)  # RFID Tag UID on physical copy
    status = Column(String(30), default="AVAILABLE", nullable=False)  # AVAILABLE, CHECKED_OUT, IN_TRANSIT, LOST
    shelf_location = Column(String(100), default="Main Stacks A-1", nullable=False)
    last_seen_reader_id = Column(String(50), nullable=True)
    last_seen_at = Column(DateTime, nullable=True)

    book = relationship("Book", back_populates="copies")
    loans = relationship("Loan", back_populates="copy")

class Reader(Base):
    __tablename__ = "readers"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, index=True, nullable=False)  # e.g., CHECKOUT-01, RETURN-01, GATE-01, SHELF-01
    name = Column(String(100), nullable=False)
    reader_type = Column(String(30), nullable=False)  # CHECKOUT, RETURN, SHELF, EXIT_GATE
    secret_key = Column(String(128), nullable=False)  # Pre-shared HMAC key
    location = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_heartbeat = Column(DateTime, nullable=True)
    total_scans = Column(Integer, default=0, nullable=False)

class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    copy_id = Column(Integer, ForeignKey("book_copies.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    checkout_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    due_date = Column(DateTime, nullable=False)
    returned_at = Column(DateTime, nullable=True)
    renewal_count = Column(Integer, default=0, nullable=False)
    fine_amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, RETURNED, OVERDUE

    copy = relationship("BookCopy", back_populates="loans")
    member = relationship("Member", back_populates="loans")

class CheckoutSession(Base):
    __tablename__ = "checkout_sessions"

    id = Column(Integer, primary_key=True, index=True)
    reader_id = Column(String(50), index=True, nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    status = Column(String(20), default="OPEN", nullable=False)  # OPEN, COMPLETED, TIMED_OUT, CANCELLED
    started_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    scanned_copies_count = Column(Integer, default=0, nullable=False)

    member = relationship("Member", back_populates="sessions")

class ScanEvent(Base):
    __tablename__ = "scan_events"

    id = Column(Integer, primary_key=True, index=True)
    reader_id = Column(String(50), index=True, nullable=False)
    tag_uid = Column(String(64), index=True, nullable=False)
    tag_type = Column(String(20), default="UNKNOWN", nullable=False)  # MEMBER_CARD, BOOK_TAG, UNKNOWN
    timestamp = Column(Integer, nullable=False)
    nonce = Column(String(64), nullable=False)
    signature_valid = Column(Boolean, default=True, nullable=False)
    result_status = Column(String(50), nullable=False)  # SUCCESS, DEBOUNCED, REPLAY_BLOCKED, ALERT_THEFT, etc.
    action_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(50), nullable=False)  # UNAUTHORIZED_EXIT, OVERDUE_DETECTED, UNREGISTERED_TAG
    severity = Column(String(20), default="CRITICAL", nullable=False)  # CRITICAL, WARNING, INFO
    reader_id = Column(String(50), nullable=True)
    copy_id = Column(Integer, ForeignKey("book_copies.id"), nullable=True)
    tag_uid = Column(String(64), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)
    resolved_by = Column(String(50), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
