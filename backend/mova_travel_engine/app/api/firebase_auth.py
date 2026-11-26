"""Firebase ID-token verification for protected MOVA API routes.

Configure GOOGLE_APPLICATION_CREDENTIALS to a Firebase service-account JSON file
outside the repository. Never commit that file.
"""
from __future__ import annotations
import os
from functools import lru_cache
from fastapi import Depends, Header, HTTPException

@lru_cache(maxsize=1)
def _firebase_admin():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise RuntimeError("Firebase Admin SDK is not installed. Install requirements.txt.") from exc
    if not firebase_admin._apps:
        credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if not credential_path:
            raise RuntimeError("Set GOOGLE_APPLICATION_CREDENTIALS to your Firebase service-account JSON path.")
        firebase_admin.initialize_app(credentials.Certificate(credential_path))
    return firebase_admin

def require_firebase_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code":"authentication_required","message":"Sign in to use this feature."})
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail={"code":"authentication_required","message":"Sign in to use this feature."})
    try:
        admin = _firebase_admin()
        return admin.auth.verify_id_token(token, check_revoked=True)
    except HTTPException:
        raise
    except Exception as exc:
        # Do not leak service-account paths or verifier internals to clients.
        if isinstance(exc, RuntimeError) and "GOOGLE_APPLICATION_CREDENTIALS" in str(exc):
            raise HTTPException(status_code=503, detail={"code":"auth_not_configured","message":"MOVA server authentication is not configured yet."}) from exc
        raise HTTPException(status_code=401, detail={"code":"invalid_auth_token","message":"Your sign-in session could not be verified. Sign in again."}) from exc

CurrentUser = Depends(require_firebase_user)
