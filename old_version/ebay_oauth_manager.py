import base64
import json
import os
import requests
import sys

# === READ FROM EXISTING FILES ===
def read_file(filename):
    if not os.path.exists(filename):
        print(f"Missing file: {filename}")
        sys.exit(1)
    return open(filename).read().strip()

CLIENT_ID = read_file("client_id.txt")
CLIENT_SECRET = read_file("client_secret.txt")
RUNAME = read_file("ru_name.txt")
SCOPE = "https://api.ebay.com/oauth/api_scope"
TOKEN_FILE = "accessToken.txt"
REFRESH_FILE = "refresh_token.txt"


def get_auth_url():
    url = (
        f"https://auth.ebay.com/oauth2/authorize?"
        f"client_id={CLIENT_ID}&response_type=code&"
        f"redirect_uri={RUNAME}&scope={SCOPE}&state=rytona1"
    )
    print("\n👉 Open this URL in your browser:")
    print(url)
    print("\nAfter approving, copy the `code` value from the redirected URL.")
    return url


def get_basic_auth_header():
    creds = f"{CLIENT_ID}:{CLIENT_SECRET}"
    return base64.b64encode(creds.encode()).decode()


def exchange_code(auth_code):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {get_basic_auth_header()}",
    }
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": RUNAME,
    }

    resp = requests.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)
    if resp.status_code != 200:
        print("❌ Exchange failed:", resp.text)
        sys.exit(1)

    tokens = resp.json()
    print(json.dumps(tokens, indent=2))

    open(TOKEN_FILE, "w").write(tokens["access_token"])
    open(REFRESH_FILE, "w").write(tokens["refresh_token"])
    print("✅ Tokens saved.")


def refresh_token():
    refresh = read_file(REFRESH_FILE)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {get_basic_auth_header()}",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "scope": SCOPE,
    }

    resp = requests.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)
    if resp.status_code != 200:
        print("❌ Refresh failed:", resp.text)
        sys.exit(1)

    new_token = resp.json()["access_token"]
    open(TOKEN_FILE, "w").write(new_token)
    print("✅ Access token refreshed.")


def get_user():
    token = read_file(TOKEN_FILE)
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": "GetUser",
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
        "X-EBAY-API-IAF-TOKEN": token,
    }
    xml_body = """<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents"></GetUserRequest>"""

    resp = requests.post("https://api.ebay.com/ws/api.dll", headers=headers, data=xml_body)
    print(resp.text)


def main():
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python ebay_oauth_manager.py auth-url\n"
            "  python ebay_oauth_manager.py exchange <AUTH_CODE>\n"
            "  python ebay_oauth_manager.py refresh\n"
            "  python ebay_oauth_manager.py getuser"
        )
        return

    cmd = sys.argv[1].lower()
    if cmd == "auth-url":
        get_auth_url()
    elif cmd == "exchange":
        if len(sys.argv) < 3:
            print("Usage: python ebay_oauth_manager.py exchange <AUTH_CODE>")
            return
        exchange_code(sys.argv[2])
    elif cmd == "refresh":
        refresh_token()
    elif cmd == "getuser":
        get_user()
    else:
        print("Unknown command.")


if __name__ == "__main__":
    main()
