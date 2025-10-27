# ebay_auth.py
import base64, json, os, time, sys, requests
from urllib.parse import unquote


# ---- file paths (match your current files) ----
CLIENT_ID_FILE = "client_id.txt"
CLIENT_SECRET_FILE = "client_secret.txt"
RUNAME_FILE = "ru_name.txt"
ACCESS_FILE = "accessToken.txt"
REFRESH_FILE = "refresh_token.txt"
META_FILE = "token_meta.json"   # we'll store expires info here

SCOPE = "https://api.ebay.com/oauth/api_scope"

def _read(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing file: {path}")
    return open(path).read().strip()

def _auth_header():
    cid = _read(CLIENT_ID_FILE)
    cs  = _read(CLIENT_SECRET_FILE)
    return base64.b64encode(f"{cid}:{cs}".encode()).decode()

def auth_url(state="rytona1"):
    cid = _read(CLIENT_ID_FILE)
    runame = _read(RUNAME_FILE)
    return (
        "https://auth.ebay.com/oauth2/authorize"
        f"?client_id={cid}"
        "&response_type=code"
        f"&redirect_uri={runame}"
        f"&scope={SCOPE}"
        f"&state={state}"
    )

def exchange_code(auth_code: str):
    """One-time: turn the 'code' from the browser into access+refresh tokens."""
    # Decode URL-encoded characters like %5E and %23
    auth_code = unquote(auth_code.strip())

    runame = _read(RUNAME_FILE)
    r = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {_auth_header()}",
        },
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": runame,
        },
        timeout=30,
    )

    if r.status_code != 200:
        # Print full context for debugging if eBay rejects the code
        print(f"\n❌ Exchange failed ({r.status_code}): {r.text}\n")
        raise RuntimeError(f"Exchange failed: {r.status_code} {r.text}")

    data = r.json()

    # Save tokens
    open(ACCESS_FILE, "w").write(data["access_token"])
    open(REFRESH_FILE, "w").write(data["refresh_token"])
    json.dump(
        {"obtained_at": int(time.time()), "expires_in": int(data.get("expires_in", 7200))},
        open(META_FILE, "w"),
    )

    print("\n✅ Exchange successful — access & refresh tokens saved.\n")
    return data

def _expired() -> bool:
    try:
        meta = json.load(open(META_FILE))
        return (time.time() - meta["obtained_at"]) >= (meta["expires_in"] - 120)  # 2 min cushion
    except Exception:
        # if meta missing or malformed, treat as expired to force refresh-check
        return True

def _validate_access(token: str) -> bool:
    """Light ping; returns False if token invalid/expired."""
    try:
        r = requests.get(
            "https://api.ebay.com/commerce/identity/v1/user/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code == 200:
            return True
        # 401/403 or known text means invalid IAF token
        return False
    except Exception:
        return False

def refresh_access():
    """Use refresh token to obtain a new access token (keeps same refresh)."""
    refresh = _read(REFRESH_FILE)
    r = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {_auth_header()}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "scope": SCOPE,
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Refresh failed: {r.status_code} {r.text}")
    data = r.json()
    open(ACCESS_FILE, "w").write(data["access_token"])
    json.dump(
        {"obtained_at": int(time.time()), "expires_in": int(data.get("expires_in", 7200))},
        open(META_FILE, "w"),
    )
    return data

def get_access_token() -> str:
    """
    Return a valid access token.
    - If we think it’s fresh via META, return it.
    - Else validate; if invalid/expired -> refresh and return the new one.
    """
    token = _read(ACCESS_FILE) if os.path.exists(ACCESS_FILE) else ""
    if token and not _expired() and _validate_access(token):
        return token

    # try one validation even if meta says fresh (handles manual edits)
    if token and _validate_access(token):
        return token

    # fallback: refresh
    refresh_access()
    return _read(ACCESS_FILE)

# --- tiny CLI for convenience ---
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="eBay OAuth helper")
    p.add_argument(
        "cmd",
        choices=["auth-url", "exchange", "refresh", "print-token", "getuser"],
        help="Select a command to run",
    )
    p.add_argument("--code", help="Authorization code for 'exchange'")
    args = p.parse_args()

    if args.cmd == "auth-url":
        print(auth_url())

    elif args.cmd == "exchange":
        if not args.code:
            sys.exit("❌ Please provide --code=YOUR_AUTH_CODE")
        data = exchange_code(args.code)
        print(json.dumps(data, indent=2))

    elif args.cmd == "refresh":
        data = refresh_access()
        print(json.dumps(data, indent=2))

    elif args.cmd == "print-token":
        print(get_access_token())

    elif args.cmd == "getuser":
        token = get_access_token()
        headers = {
            "Content-Type": "text/xml",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-IAF-TOKEN": token,
        }
        xml_body = """<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents"></GetUserRequest>"""
        r = requests.post("https://api.ebay.com/ws/api.dll", headers=headers, data=xml_body)
        print("\n--- eBay GetUser Response ---\n")
        print(r.text)
        print("\n------------------------------\n")
