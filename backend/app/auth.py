import os

# Allow token when Google returns fewer scopes than requested (e.g. drive.file not granted yet)
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from datetime import datetime
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import (
    BACKEND_URL,
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
)
from app.db import (
    get_user_credentials_metadata,
    update_user_tokens,
    upsert_user as vs_upsert_user,
)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",
]


def get_authorization_url():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"{BACKEND_URL}/auth/google/callback"],
            }
        },
        scopes=SCOPES,
        redirect_uri=f"{BACKEND_URL}/auth/google/callback",
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def exchange_code_for_tokens(code: str, timeout: int = 30):
    """Exchange an OAuth authorization code for credentials.

    Args:
        code: The authorization code from Google.
        timeout: HTTP request timeout in seconds (default 30).
    """
    import requests

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"{BACKEND_URL}/auth/google/callback"],
            }
        },
        scopes=SCOPES,
        redirect_uri=f"{BACKEND_URL}/auth/google/callback",
    )
    # Mount a session with an explicit timeout so fetch_token never hangs indefinitely.
    session = requests.Session()
    session.request = lambda method, url, **kwargs: requests.Session.request(
        session, method, url, timeout=timeout, **kwargs
    )
    flow.fetch_token(code=code, session=session)
    credentials = flow.credentials
    return credentials


def get_user_info(credentials, timeout: int = 30) -> dict:
    """Fetch user info from Google using the credentials.

    Args:
        credentials: OAuth2 credentials object.
        timeout: HTTP request timeout in seconds (default 30).
    """
    import httplib2

    from googleapiclient.discovery import build

    # httplib2 is used under the hood by google-api-python-client; set a socket timeout.
    http = httplib2.Http(timeout=timeout)
    authed_http = credentials.authorize(http)
    service = build("oauth2", "v2", http=authed_http)
    userinfo = service.userinfo().get().execute()
    return userinfo


def upsert_user(google_id: str, email: str, name: str, credentials) -> int:
    """Insert or update user with tokens. Returns user_id."""
    expiry = credentials.expiry.timestamp() if credentials.expiry else None
    return vs_upsert_user(
        google_id=google_id,
        email=email,
        name=name or email,
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_expiry=expiry,
    )


def get_user_credentials(user_id: int) -> Credentials | None:
    """Get valid OAuth credentials for a user. Refreshes if expired."""
    from datetime import datetime
    from google.auth.transport.requests import Request

    row = get_user_credentials_metadata(user_id)
    if not row:
        return None

    creds = Credentials(
        token=row["access_token"],
        refresh_token=row["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        expiry = creds.expiry.timestamp() if creds.expiry else None
        update_user_tokens(user_id, creds.token, expiry)
    return creds
