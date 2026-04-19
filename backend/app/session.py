import base64
import json
import secrets
from typing import Optional

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import SECRET_KEY

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="chipmunk-session")


def create_session(user_id: int) -> str:
    """Create a signed session token."""
    payload = {"user_id": user_id}
    return serializer.dumps(payload)


def get_session(session_token: str) -> Optional[int]:
    """Validate session and return user_id. Returns None if invalid."""
    try:
        payload = serializer.loads(session_token, max_age=7 * 24 * 3600)
        return payload.get("user_id")
    except BadSignature:
        return None
