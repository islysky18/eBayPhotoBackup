# Copyright (c) 2025 islysky18
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#
# ebay_auth.py
# Core OAuth helpers for eBay (Production). Supports auth URL generation,
# authorization-code exchange, refresh, and token management.
#
# Files required (place in same folder):
#   client_id.txt       -> App ID (Client ID)
#   client_secret.txt   -> Cert ID (Client Secret)
#   ru_name.txt         -> Your Redirect URI (RuName) from eBay dev portal
#
# Files produced:
#   accessToken.txt     -> Short-lived OAuth access token (IAF token for Trading API)
#   refresh_token.txt   -> Long-lived refresh token
#
# Usage examples (see ebay_oauth_manager.py for CLI):
#   from ebay_auth import ensure_access_token, build_consent_url
#   print(build_consent_url(scope=["https://api.ebay.com/oauth/api_scope"]))
#   token = ensure_access_token()

import base64
import json
import os
import time
from pathlib import Path
from typing import List, Optional
import requests
from urllib.parse import unquote

EBAY_OAUTH_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

ACCESS_FILE = Path("accessToken.txt")
REFRESH_FILE = Path("refresh_token.txt")
CLIENT_ID_FILE = Path("client_id.txt")
CLIENT_SECRET_FILE = Path("client_secret.txt")
RUNAME_FILE = Path("ru_name.txt")

# Default scopes: Trading IAF access needs a user token scope; the broad scope works for most use
DEFAULT_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.marketing.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.marketing",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
]

def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path.name}")
    return path.read_text(encoding="utf-8").strip()

def _basic_auth_header() -> str:
    cid = _read_text(CLIENT_ID_FILE)
    csec = _read_text(CLIENT_SECRET_FILE)
    creds = f"{cid}:{csec}".encode("utf-8")
    return base64.b64encode(creds).decode("utf-8")

def build_consent_url(scope: Optional[List[str]] = None, state: str = "ebay_oauth_state") -> str:
    """Return the user-consent URL to obtain an auth code (grant_type=authorization_code).
    Open this in a browser, sign in, and you'll be redirected to your RUNAME with ?code=<AUTH_CODE>.
    """
    scopes = scope or DEFAULT_SCOPES
    runame = _read_text(RUNAME_FILE)
    cid = _read_text(CLIENT_ID_FILE)
    # Trading uses the same authorization code grant. We request user scope(s).
    params = {
        "client_id": cid,
        "redirect_uri": runame,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        # Prompt login screen every time so you're not surprised about which user you authenticated
        "prompt": "login",
    }
    from urllib.parse import urlencode
    return f"https://auth.ebay.com/oauth2/authorize?{urlencode(params)}"

def exchange_code_for_tokens(auth_code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens; persist both to disk."""
    auth_code = unquote(auth_code)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {_basic_auth_header()}",
    }
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": _read_text(RUNAME_FILE),
    }
    r = requests.post(EBAY_OAUTH_TOKEN_URL, headers=headers, data=data, timeout=45)
    r.raise_for_status()
    payload = r.json()
    ACCESS_FILE.write_text(payload["access_token"], encoding="utf-8")
    if "refresh_token" in payload:
        REFRESH_FILE.write_text(payload["refresh_token"], encoding="utf-8")
    # Persist expiry metadata (seconds)
    meta = {
        "expires_in": payload.get("expires_in"),
        "created_at": int(time.time()),
    }
    Path("access_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return payload

def refresh_access_token() -> dict:
    """Refresh using refresh_token.txt; writes new accessToken.txt."""
    refresh_token = _read_text(REFRESH_FILE)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {_basic_auth_header()}",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        # Required for refresh in some flows: include the scopes that the refresh token was granted
        "scope": " ".join(DEFAULT_SCOPES),
    }
    r = requests.post(EBAY_OAUTH_TOKEN_URL, headers=headers, data=data, timeout=45)
    r.raise_for_status()
    payload = r.json()
    ACCESS_FILE.write_text(payload["access_token"], encoding="utf-8")
    # refresh_token often rotates; save if present
    if "refresh_token" in payload:
        REFRESH_FILE.write_text(payload["refresh_token"], encoding="utf-8")
    meta = {
        "expires_in": payload.get("expires_in"),
        "created_at": int(time.time()),
    }
    Path("access_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return payload

def _is_access_token_fresh(leeway_seconds: int = 60) -> bool:
    try:
        meta = json.loads(Path("access_meta.json").read_text(encoding="utf-8"))
        created = meta.get("created_at", 0)
        ttl = meta.get("expires_in", 0)
        return (time.time() + leeway_seconds) < (created + ttl)
    except Exception:
        return False

def ensure_access_token() -> str:
    """Return a valid access token, attempting refresh if needed."""
    if ACCESS_FILE.exists() and _is_access_token_fresh():
        return ACCESS_FILE.read_text(encoding="utf-8").strip()
    # Try refresh if we have a refresh token
    if REFRESH_FILE.exists():
        payload = refresh_access_token()
        return payload["access_token"]
    raise RuntimeError("No fresh access token available and refresh_token.txt is missing. Run the consent flow first.")

# Trading API helper (XML over HTTP). Use IAF token (OAuth access token) in header.
def trading_call(call_name: str, xml_body: str, site_id: int = 0, compatibility_level: int = 967) -> requests.Response:
    token = ensure_access_token()
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": str(site_id),
        "X-EBAY-API-COMPATIBILITY-LEVEL": str(compatibility_level),
        "X-EBAY-API-IAF-TOKEN": token,
    }
    url = "https://api.ebay.com/ws/api.dll"
    return requests.post(url, headers=headers, data=xml_body.encode("utf-8"), timeout=60)
