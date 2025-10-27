#!/usr/bin/env python3
"""
eBay Image Backup – downloads PictureURL links for every listing.

Steps
-----
1. Paste your OAuth access token below.
2. Adjust START_DATE / END_DATE if desired.
3. Run:  pip install requests python-dateutil
         python ebay_image_backup.py
"""

import csv, os, time, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pathlib import Path
import requests

# ========= USER CONFIG =========
# Read token from external file
TOKEN_FILE = Path("token.txt")
ACCESS_TOKEN = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""

if not ACCESS_TOKEN:
    raise SystemExit("⚠️  No access token found! Please create token.txt with your OAuth token.")


#ACCESS_TOKEN = "v^1.1#i^1#p^3#f^0#I^3#r^0#t^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"

# Date range (UTC)
START_DATE = "2024-01-01"
END_DATE   = datetime.utcnow().strftime("%Y-%m-%d")

ENTRIES_PER_PAGE = 100          # up to 200 allowed
SLEEP_BETWEEN_CALLS = 0.6       # seconds between calls
COMPAT_LEVEL = "967"

OUT_DIR = Path("out")
CSV_PATH = OUT_DIR / "image_urls.csv"
IMAGES_DIR = OUT_DIR / "images"

DOWNLOAD_TIMEOUT = 30
DOWNLOAD_RETRIES = 3
# ========= END CONFIG =========

TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
NAMESP = {"e": "urn:ebay:apis:eBLBaseComponents"}

def ensure_dirs():
    OUT_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def month_windows(start_date_str, end_date_str):
    """Yield (start_iso, end_iso) monthly ISO windows inclusive."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end = datetime.strptime(end_date_str, "%Y-%m-%d")
    cur = datetime(start.year, start.month, 1)
    while cur <= end:
        next_month = cur + relativedelta(months=1)
        yield (
            cur.strftime("%Y-%m-%dT00:00:00.000Z"),
            (next_month - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )
        cur = next_month

def trading_call(call_name: str, xml_body: str) -> ET.Element:
    """POST XML to Trading API and return parsed ElementTree root."""
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT_LEVEL,
        "X-EBAY-API-IAF-TOKEN": ACCESS_TOKEN,
    }
    resp = requests.post(TRADING_ENDPOINT, data=xml_body.encode("utf-8"), headers=headers, timeout=90)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ack = root.findtext("e:Ack", namespaces=NAMESP)
    if ack not in ("Success", "Warning"):
        errs = root.findall(".//e:Errors", namespaces=NAMESP)
        details = "; ".join(
            f"{e.findtext('e:SeverityCode', default='', namespaces=NAMESP)} "
            f"{e.findtext('e:ShortMessage', default='', namespaces=NAMESP)} "
            f"{e.findtext('e:LongMessage', default='', namespaces=NAMESP)}"
            for e in errs
        )
        raise RuntimeError(f"{call_name} Ack={ack}. {details or 'Unknown error.'}")
    return root

def get_seller_list_page(start_iso: str, end_iso: str, page: int) -> ET.Element:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnAll</DetailLevel>
  <GranularityLevel>Fine</GranularityLevel>
  <Pagination>
    <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
  <StartTimeFrom>{start_iso}</StartTimeFrom>
  <StartTimeTo>{end_iso}</StartTimeTo>
  <IncludeVariations>true</IncludeVariations>
</GetSellerListRequest>
"""
    return trading_call("GetSellerList", xml)

def iter_items(root: ET.Element):
    """Yield (ItemID, SKU, [picture_urls...]) from a GetSellerListResponse root."""
    for item in root.findall(".//e:Item", namespaces=NAMESP):
        item_id = item.findtext("e:ItemID", default="", namespaces=NAMESP)
        sku = item.findtext("e:SKU", default="", namespaces=NAMESP)
        pic_urls = [u.text for u in item.findall(".//e:PictureDetails/e:PictureURL", namespaces=NAMESP) if u.text]
        gal = item.findtext(".//e:GalleryURL", default="", namespaces=NAMESP)
        if gal:
            pic_urls.append(gal)
        seen, uniq = set(), []
        for u in pic_urls:
            if u not in seen:
                uniq.append(u)
                seen.add(u)
        yield item_id, sku, uniq

def append_rows_to_csv(rows):
    file_exists = CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "sku", "image_url"])
        if not file_exists:
            w.writeheader()
        w.writerows(rows)

def download_image(url: str, dest_path: Path):
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            r = requests.get(url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
            if r.ok and r.content:
                dest_path.write_bytes(r.content)
                return True
        except Exception:
            pass
        time.sleep(1.5 * attempt)
    return False

def sanitize_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", "+"))[:200]

def main():
    if not ACCESS_TOKEN or ACCESS_TOKEN.startswith("PASTE_"):
        raise SystemExit("➡️  Please paste your ACCESS_TOKEN at the top of the script and run again.")

    ensure_dirs()
    print(f"Saving CSV to: {CSV_PATH.resolve()}")
    print(f"Saving images under: {IMAGES_DIR.resolve()}")

    total_items = 0
    total_images = 0

    for start_iso, end_iso in month_windows(START_DATE, END_DATE):
        print(f"\n=== Window {start_iso[:10]} → {end_iso[:10]} ===")
        page = 1
        while True:
            try:
                root = get_seller_list_page(start_iso, end_iso, page)
            except Exception as e:
                print(f"GetSellerList error on page {page}: {e}")
                break

            total_pages = root.findtext(".//e:PaginationResult/e:TotalNumberOfPages", namespaces=NAMESP)
            total_pages = int(total_pages) if total_pages and total_pages.isdigit() else page

            batch_rows = []
            item_count_this_page = 0

            for item_id, sku, urls in iter_items(root):
                item_count_this_page += 1
                total_items += 1
                for u in urls:
                    batch_rows.append({"item_id": item_id, "sku": sku, "image_url": u})
                if urls:
                    item_dir = IMAGES_DIR / item_id
                    item_dir.mkdir(parents=True, exist_ok=True)
                    for u in urls:
                        base = sanitize_filename(u.split("/")[-1].split("?")[0] or "img.jpg")
                        dest = item_dir / base
                        if dest.exists():
                            continue
                        if download_image(u, dest):
                            total_images += 1
                        time.sleep(0.2)

            append_rows_to_csv(batch_rows)
            print(f"Page {page}/{total_pages} → items:{item_count_this_page}, images_downloaded_so_far:{total_images}")
            page += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
            if page > total_pages:
                break

    print("\n==== DONE ====")
    print(f"Total items seen: {total_items}")
    print(f"Images downloaded: {total_images}")
    print(f"CSV at: {CSV_PATH.resolve()}")
    print(f"Images at: {IMAGES_DIR.resolve()}")

if __name__ == "__main__":
    main()
