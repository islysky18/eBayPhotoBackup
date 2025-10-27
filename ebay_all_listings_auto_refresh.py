#!/usr/bin/env python3
# eBay ALL Listings backup with AUTO-REFRESH
import csv, time, base64, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta
import requests
from ebay_auth import get_access_token
import requests
from ebay_auth import get_access_token


# ---------- Files ----------
TOKEN_FILE = Path("accessToken.txt")
REFRESH_FILE = Path("refresh_token.txt")
CLIENT_ID_FILE = Path("client_id.txt")
CLIENT_SECRET_FILE = Path("client_secret.txt")
RU_NAME_FILE = Path("ru_name.txt")

ACCESS_TOKEN = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
REFRESH_TOKEN = REFRESH_FILE.read_text().strip() if REFRESH_FILE.exists() else ""
CLIENT_ID = CLIENT_ID_FILE.read_text().strip() if CLIENT_ID_FILE.exists() else ""
CLIENT_SECRET = CLIENT_SECRET_FILE.read_text().strip() if CLIENT_SECRET_FILE.exists() else ""
RU_NAME = RU_NAME_FILE.read_text().strip() if RU_NAME_FILE.exists() else ""

if not ACCESS_TOKEN:
    raise SystemExit("⚠️ token.txt missing/empty")

# ---------- Config ----------
START_DATE = "2024-09-01"
END_DATE   = datetime.utcnow().strftime("%Y-%m-%d")
ENTRIES_PER_PAGE = 200
SLEEP_BETWEEN_CALLS = 0.6
DOWNLOAD_IMAGES = True
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_RETRIES = 3
COMPAT_LEVEL = "967"

OUT_DIR = Path("out_all")
CSV_PATH = OUT_DIR / "image_urls.csv"
IMAGES_DIR = OUT_DIR / "images_by_sku"
OUT_DIR.mkdir(exist_ok=True); IMAGES_DIR.mkdir(parents=True, exist_ok=True)

TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
IDENTITY_ENDPOINT = "https://api.ebay.com/identity/v1/oauth2/token"
NAMESP = {"e": "urn:ebay:apis:eBLBaseComponents"}

def month_windows(s, e):
    start = datetime.strptime(s, "%Y-%m-%d")
    end = datetime.strptime(e, "%Y-%m-%d")
    cur = datetime(start.year, start.month, 1)
    while cur <= end:
        nxt = cur + relativedelta(months=1)
        yield (cur.strftime("%Y-%m-%dT00:00:00.000Z"),
               (nxt - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        cur = nxt

def sanitize(name: str) -> str:
    name = (name or "").strip() or "NO_SKU"
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", "+"))[:200]

def _do_trading_post(call_name, xml_body, token):
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT_LEVEL,
        "X-EBAY-API-IAF-TOKEN": token,
    }
    return requests.post(TRADING_ENDPOINT, data=xml_body.encode("utf-8"),
                         headers=headers, timeout=90)

def refresh_access_token():
    """Use refresh token to mint a new access token and persist it to token.txt"""
    global ACCESS_TOKEN
    if not (REFRESH_TOKEN and CLIENT_ID and CLIENT_SECRET):
        raise RuntimeError("No refresh setup. Put refresh_token.txt, client_id.txt, client_secret.txt")
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "scope": "https://api.ebay.com/oauth/api_scope",
    }
    r = requests.post(IDENTITY_ENDPOINT,
                      headers={"Authorization": f"Basic {basic}",
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data=data, timeout=60)
    r.raise_for_status()
    js = r.json()
    new_token = js.get("access_token")
    if not new_token:
        raise RuntimeError(f"Refresh failed: {r.text}")
    ACCESS_TOKEN = new_token
    TOKEN_FILE.write_text(new_token)
    print("🔄 Access token refreshed and saved to token.txt")

def trading_call(call_name: str, xml_body: str) -> ET.Element:
    # First attempt
    resp = _do_trading_post(call_name, xml_body, ACCESS_TOKEN)
    text = resp.text
    # If HTTP 401, try refresh once
    if resp.status_code == 401 and REFRESH_TOKEN:
        print("⚠️  HTTP 401: attempting token refresh…")
        refresh_access_token()
        resp = _do_trading_post(call_name, xml_body, ACCESS_TOKEN)
        text = resp.text

    resp.raise_for_status()
    root = ET.fromstring(text)

    ack = root.findtext("e:Ack", namespaces=NAMESP)
    if ack not in ("Success", "Warning"):
        # Detect expired token inside XML errors
        errs = root.findall(".//e:Errors", namespaces=NAMESP)
        messages = []
        expired = False
        for e in errs:
            sm = e.findtext("e:ShortMessage", default="", namespaces=NAMESP) or ""
            lm = e.findtext("e:LongMessage", default="", namespaces=NAMESP) or ""
            messages.append(f"{sm} {lm}".strip())
            if "Expired IAF token" in sm or "Expired IAF token" in lm:
                expired = True
        if expired and REFRESH_TOKEN:
            print("⚠️  Ack=Failure due to expired token. Refreshing…")
            refresh_access_token()
            resp2 = _do_trading_post(call_name, xml_body, ACCESS_TOKEN)
            resp2.raise_for_status()
            root = ET.fromstring(resp2.text)
            ack2 = root.findtext("e:Ack", namespaces=NAMESP)
            if ack2 in ("Success", "Warning"):
                return root
            else:
                raise RuntimeError(f"{call_name} failed after refresh. {messages}")
        raise RuntimeError(f"{call_name} Ack={ack}. {'; '.join(messages) or 'Unknown error.'}")
    return root

def get_seller_list_page(page: int, window_type: str, start_iso: str, end_iso: str) -> ET.Element:
    tag_from = f"{window_type}From"; tag_to = f"{window_type}To"
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnAll</DetailLevel>
  <GranularityLevel>Fine</GranularityLevel>
  <Pagination>
    <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
  <{tag_from}>{start_iso}</{tag_from}>
  <{tag_to}>{end_iso}</{tag_to}>
  <IncludeVariations>true</IncludeVariations>
</GetSellerListRequest>"""
    return trading_call("GetSellerList", xml)

def iter_items(root: ET.Element):
    for item in root.findall(".//e:Item", namespaces=NAMESP):
        item_id = item.findtext("e:ItemID", "", NAMESP)
        sku = item.findtext("e:SKU", "", NAMESP)
        urls = [u.text for u in item.findall(".//e:PictureDetails/e:PictureURL", namespaces=NAMESP) if u.text]
        gal = item.findtext(".//e:GalleryURL", "", NAMESP)
        if gal:
            urls.append(gal)
        seen, uniq = set(), []
        for u in urls:
            if u and u not in seen:
                uniq.append(u); seen.add(u)
        yield item_id, sku, uniq

def append_rows(rows):
    file_exists = CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item_id","sku","image_url","source","window_start","window_end"])
        if not file_exists:
            w.writeheader()
        w.writerows(rows)

def download_image(url: str, dest: Path) -> bool:
    for attempt in range(1, DOWNLOAD_RETRIES+1):
        try:
            r = requests.get(url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
            if r.ok and r.content:
                dest.write_bytes(r.content)
                return True
        except Exception:
            pass
        time.sleep(1.2 * attempt)
    return False

def process_window(window_type: str, start_iso: str, end_iso: str, seen_ids: set, counters: dict):
    print(f"\n=== {window_type} window {start_iso[:10]} → {end_iso[:10]} ===")
    page = 1
    while True:
        try:
            root = get_seller_list_page(page, window_type, start_iso, end_iso)
        except Exception as e:
            print(f"{window_type} page {page} error: {e}")
            break
        total_pages_txt = root.findtext(".//e:PaginationResult/e:TotalNumberOfPages", namespaces=NAMESP)
        total_pages = int(total_pages_txt) if total_pages_txt and total_pages_txt.isdigit() else page

        batch, items_this_page = [], 0
        for item_id, sku, urls in iter_items(root):
            if not item_id: continue
            if item_id in seen_ids and not urls: continue
            seen_ids.add(item_id)
            items_this_page += 1; counters["items"] += 1

            for u in urls:
                batch.append({"item_id": item_id, "sku": sku, "image_url": u,
                              "source": window_type, "window_start": start_iso, "window_end": end_iso})

            if DOWNLOAD_IMAGES and urls:
                label = sanitize(sku or item_id)
                folder = IMAGES_DIR / label; folder.mkdir(parents=True, exist_ok=True)
                for i, u in enumerate(urls, start=1):
                    fname = f"{label}.jpg" if len(urls)==1 else f"{label}_{i}.jpg"
                    dest = folder / fname
                    if dest.exists(): continue
                    if download_image(u, dest): counters["images"] += 1
                    time.sleep(0.2)

        append_rows(batch)
        print(f"{window_type} Page {page}/{total_pages} → items:{items_this_page}, images_so_far:{counters['images']}")
        page += 1
        time.sleep(SLEEP_BETWEEN_CALLS)
        if page > total_pages:
            break

def main():
    print(f"CSV → {CSV_PATH.resolve()}")
    print(f"Images → {IMAGES_DIR.resolve()}")
    print(f"Date Range: {START_DATE} → {END_DATE}")
    counters = {"items": 0, "images": 0}; seen_ids = set()

    for s,e in month_windows(START_DATE, END_DATE): process_window("StartTime", s, e, seen_ids, counters)
    for s,e in month_windows(START_DATE, END_DATE): process_window("EndTime",   s, e, seen_ids, counters)
    for s,e in month_windows(START_DATE, END_DATE): process_window("ModTime",   s, e, seen_ids, counters)

    print("\n==== DONE ====")
    print(f"Unique items: {len(seen_ids)}  |  Images downloaded: {counters['images']}")
    print(f"CSV at: {CSV_PATH.resolve()}")

if __name__ == "__main__":
    main()
