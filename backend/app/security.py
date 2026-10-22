import time
import hmac
import hashlib
import datetime
from typing import Optional, Dict, Tuple, Set
import bcrypt
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

# Security schemes
security_scheme = HTTPBearer(auto_error=False)

# In-memory sliding caches for edge security
# In a distributed multi-node cloud, this can map to Redis with TTL
_seen_nonces: Dict[str, float] = {}  # key: f"{device_id}:{nonce}", value: timestamp
_last_scan_times: Dict[str, float] = {}  # key: f"{device_id}:{tag_uid}", value: timestamp

# ---------------- Password Hashing ----------------
def hash_password(password: str) -> str:
    pwd_bytes = password[:72].encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password[:72].encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode('utf-8'))
    except Exception:
        return False

# ---------------- JWT Tokens ----------------
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.datetime.utcnow()})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

# ---------------- RBAC Dependency ----------------
def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
):
    from app.models import User
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(auth.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload["sub"]
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_roles(allowed_roles: list[str]):
    def role_checker(current_user = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: requires role in {allowed_roles}, your role is '{current_user.role}'"
            )
        return current_user
    return role_checker

# ---------------- RFID HMAC & Edge Verification (M2) ----------------
def generate_hmac_signature(device_id: str, tag_uid: str, timestamp: int, nonce: str, secret_key: str) -> str:
    """Helper used by simulators and edge readers to compute standard HMAC-SHA256 signature."""
    payload = f"{device_id}:{tag_uid}:{timestamp}:{nonce}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()

def verify_hmac_signature(
    device_id: str,
    tag_uid: str,
    timestamp: int,
    nonce: str,
    provided_signature: str,
    secret_key: str
) -> bool:
    """Verifies that the scan payload was signed by an authentic edge reader with the shared secret key."""
    expected_signature = generate_hmac_signature(device_id, tag_uid, timestamp, nonce, secret_key)
    return hmac.compare_digest(expected_signature.lower(), provided_signature.lower())

def check_replay_attack(device_id: str, timestamp: int, nonce: str) -> Tuple[bool, str]:
    """
    Guards against replay attacks:
    1. Timestamp must fall within +/- HMAC_REPLAY_WINDOW_SECONDS of server current time.
    2. Nonce must be unique within the replay window.
    """
    current_time = time.time()
    time_delta = abs(current_time - timestamp)

    if time_delta > settings.HMAC_REPLAY_WINDOW_SECONDS:
        return False, f"Timestamp rejected: clock drift {time_delta:.1f}s exceeds window of {settings.HMAC_REPLAY_WINDOW_SECONDS}s"

    # Purge old nonces older than 2x window
    cutoff = current_time - (settings.HMAC_REPLAY_WINDOW_SECONDS * 2)
    expired_keys = [k for k, v in _seen_nonces.items() if v < cutoff]
    for k in expired_keys:
        _seen_nonces.pop(k, None)

    nonce_key = f"{device_id}:{nonce}"
    if nonce_key in _seen_nonces:
        return False, "Replay attack detected: Nonce has already been consumed"

    _seen_nonces[nonce_key] = current_time
    return True, "Valid replay window"

def check_rfid_debounce(device_id: str, tag_uid: str) -> bool:
    """
    Debounces duplicate reads. Real RFID hardware fires 3-5 bursts per pass.
    Returns True if this read is a duplicate (to be ignored/debounced).
    Returns False if this is a fresh read (updates timestamp).
    """
    current_time = time.time()
    key = f"{device_id}:{tag_uid}"
    last_time = _last_scan_times.get(key)

    if last_time is not None:
        elapsed = current_time - last_time
        if elapsed < settings.RFID_DEBOUNCE_WINDOW_SECONDS:
            return True  # Is a duplicate read

    _last_scan_times[key] = current_time

    # Periodic cleanup of debounce cache
    if len(_last_scan_times) > 10000:
        cutoff = current_time - 30.0
        stale = [k for k, v in _last_scan_times.items() if v < cutoff]
        for k in stale:
            _last_scan_times.pop(k, None)

    return False
