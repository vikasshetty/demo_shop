import os
import secrets
from passlib.context import CryptContext
from fastapi import Request, HTTPException

# bcrypt has a 72-byte password limit.
# bcrypt_sha256 pre-hashes with SHA-256 then applies bcrypt safely.
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

ENABLE_CSRF = os.environ.get("DEMO_SHOP_ENABLE_CSRF", "true").lower() == "true"
ENABLE_SECURITY_HEADERS = os.environ.get("DEMO_SHOP_SECURITY_HEADERS", "true").lower() == "true"

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def get_or_set_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token

def require_csrf(request: Request, token: str | None):
    if not ENABLE_CSRF:
        return
    expected = request.session.get("csrf_token")
    if not expected or not token or token != expected:
        raise HTTPException(status_code=403, detail="CSRF validation failed")