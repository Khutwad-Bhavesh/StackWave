import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

# ----------------- Auth & Users -----------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "member"

class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

# ----------------- Members -----------------
class MemberCreate(BaseModel):
    name: str
    email: str
    member_card_uid: str
    user_id: Optional[int] = None
    max_books: int = 5

class MemberResponse(BaseModel):
    id: int
    name: str
    email: str
    member_card_uid: str
    max_books: int
    is_active: bool
    created_at: datetime.datetime
    active_loans_count: Optional[int] = 0
    has_overdue: Optional[bool] = False
    model_config = ConfigDict(from_attributes=True)

# ----------------- Books & Copies -----------------
class BookCopyCreate(BaseModel):
    book_id: int
    tag_uid: str
    shelf_location: str = "Main Stacks A-1"

class BookCopyResponse(BaseModel):
    id: int
    book_id: int
    tag_uid: str
    status: str
    shelf_location: str
    last_seen_reader_id: Optional[str] = None
    last_seen_at: Optional[datetime.datetime] = None
    model_config = ConfigDict(from_attributes=True)

class BookCreate(BaseModel):
    title: str
    author: str
    isbn: str
    category: str = "General"
    description: Optional[str] = None

class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    isbn: str
    category: str
    description: Optional[str] = None
    created_at: datetime.datetime
    copies: List[BookCopyResponse] = []
    model_config = ConfigDict(from_attributes=True)

# ----------------- Readers -----------------
class ReaderCreate(BaseModel):
    device_id: str
    name: str
    reader_type: str  # CHECKOUT, RETURN, SHELF, EXIT_GATE
    secret_key: str
    location: str

class ReaderResponse(BaseModel):
    id: int
    device_id: str
    name: str
    reader_type: str
    location: str
    is_active: bool
    last_heartbeat: Optional[datetime.datetime] = None
    total_scans: int
    model_config = ConfigDict(from_attributes=True)

# ----------------- Ingestion & Security -----------------
class ScanIngestRequest(BaseModel):
    reader_id: str
    tag_uid: str
    timestamp: int
    nonce: str
    signature: str

class ScanIngestResponse(BaseModel):
    status: str  # success, debounced, rejected, alert
    result_code: str
    message: str
    reader_id: str
    tag_uid: str
    entity_type: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

# ----------------- Loans & Circulation -----------------
class LoanResponse(BaseModel):
    id: int
    copy_id: int
    member_id: int
    checkout_at: datetime.datetime
    due_date: datetime.datetime
    returned_at: Optional[datetime.datetime] = None
    renewal_count: int
    fine_amount: float
    status: str
    book_title: Optional[str] = None
    tag_uid: Optional[str] = None
    member_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class RenewResponse(BaseModel):
    success: bool
    message: str
    loan_id: int
    new_due_date: Optional[datetime.datetime] = None
    renewal_count: int

# ----------------- Tracking & Alerts -----------------
class TrackingItemResponse(BaseModel):
    copy_id: int
    book_title: str
    author: str
    tag_uid: str
    status: str
    shelf_location: str
    last_seen_reader_id: Optional[str] = None
    last_seen_at: Optional[datetime.datetime] = None
    current_borrower: Optional[str] = None

class AlertResponse(BaseModel):
    id: int
    alert_type: str
    severity: str
    reader_id: Optional[str] = None
    copy_id: Optional[int] = None
    tag_uid: Optional[str] = None
    message: str
    created_at: datetime.datetime
    resolved: bool
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime.datetime] = None
    model_config = ConfigDict(from_attributes=True)

class AlertResolveRequest(BaseModel):
    resolved_by: Optional[str] = "librarian"

# ----------------- Monitoring & Stats -----------------
class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    active_sessions: int
    timestamp: datetime.datetime
    uptime_seconds: float

class StatsResponse(BaseModel):
    total_books: int
    total_copies: int
    copies_available: int
    copies_checked_out: int
    total_members: int
    active_loans: int
    overdue_loans: int
    unresolved_alerts: int
    total_scans_today: int
    reader_fleet: List[Dict[str, Any]]
