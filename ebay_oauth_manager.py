# Copyright (c) 2025 islysky18
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#
# ebay_oauth_manager.py
# Simple CLI for your OAuth flow and a GetUser test.
# Commands:
#   python ebay_oauth_manager.py url
#   python ebay_oauth_manager.py exchange <AUTH_CODE>
#   python ebay_oauth_manager.py refresh
#   python ebay_oauth_manager.py getuser

import sys
from pathlib import Path
from ebay_auth import build_consent_url, exchange_code_for_tokens, refresh_access_token, trading_call, ensure_access_token

def cmd_url():
    url = build_consent_url()
    print("Open this URL to authorize:")
    print(url)

def cmd_exchange():
    if len(sys.argv) < 3:
        print("Usage: python ebay_oauth_manager.py exchange <AUTH_CODE>")
        sys.exit(1)
    auth_code = sys.argv[2]
    tokens = exchange_code_for_tokens(auth_code)
    print("✅ Tokens saved.")
    print({k: v for k, v in tokens.items() if k in ("expires_in", "refresh_token_expires_in")})

def cmd_refresh():
    payload = refresh_access_token()
    print("✅ Access token refreshed.")
    print({k: v for k, v in payload.items() if k in ("expires_in", "refresh_token_expires_in")})

def cmd_getuser():
    # Minimal Trading API test
    ensure_access_token()  # will refresh if needed
    body = '''<?xml version="1.0" encoding="utf-8"?>
    <GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    </GetUserRequest>'''
    resp = trading_call("GetUser", body)
    print("HTTP:", resp.status_code)
    print(resp.text[:1000])

def main():
    if len(sys.argv) < 2:
        print("Usage: python ebay_oauth_manager.py [url|exchange|refresh|getuser]")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    if cmd == "url":
        cmd_url()
    elif cmd == "exchange":
        cmd_exchange()
    elif cmd == "refresh":
        cmd_refresh()
    elif cmd == "getuser":
        cmd_getuser()
    else:
        print("Unknown command.")
        sys.exit(1)

if __name__ == "__main__":
    main()
