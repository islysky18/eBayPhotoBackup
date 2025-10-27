#!/usr/bin/env python3
# Copyright (c) 2025 islysky18
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#
"""
eBay ALL Listings Image Backup (Active + Ended + Revised)
- Token read from token.txt
- Initial pass: Gets ALL items (active, sold, unsold, deleted) regardless of date
- Three additional passes: StartTime, EndTime, ModTime (monthly windows)
- Images named as <SKU>.jpg (or <SKU>_2.jpg...), fallback to ItemID if no SKU
- CSV log with (item_id, sku, image_url, source, window_start, window_end)

Usage:
  1) Create token.txt with your OAuth access token (one line)
  2) pip install requests python-dateutil
  3) python ebay_all_listings_by_sku.py
"""

import csv, time, base64, xml.etree.ElementTree as ET, os
from datetime import datetime, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta
import requests
from ebay_auth import ensure_access_token

# ========= USER CONFIG =========
# Access token is now managed automatically via ebay_auth.ensure_access_token()
# Date range to cover (UTC)
START_DATE = "2018-01-01"  # Set this after running find_earliest_listing()
END_DATE   = datetime.utcnow().strftime("%Y-%m-%d")

def get_account_creation_date():
    """Get the date when the seller account was created."""
    print("Fetching account creation date...")
    try:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <DetailLevel>ReturnAll</DetailLevel>
</GetUserRequest>"""
        root = trading_call("GetUser", xml)
        registration_date = root.findtext(".//e:RegistrationDate", "", NAMESP)
        if registration_date:
            date = datetime.strptime(registration_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            print(f"Account created on: {date.strftime('%Y-%m-%d')}")
            return date
    except Exception as e:
        print(f"Error getting account creation date: {e}")
    return None

def find_earliest_listing():
    """Helper function to find your earliest listing date."""
    print("\nSearching for earliest listing date...")
    earliest = datetime.utcnow()
    page = 1
    
    # First get account creation date
    account_date = get_account_creation_date()
    if account_date:
        print(f"Note: Your account was created on {account_date.strftime('%Y-%m-%d')}")
        print("But we'll search based on your first listing date for efficiency.")
    while True:
        try:
            xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnSummary</DetailLevel>
  <GranularityLevel>Coarse</GranularityLevel>
  <Pagination>
    <EntriesPerPage>200</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
  <StartTimeFrom>2000-01-01T00:00:00.000Z</StartTimeFrom>
  <StartTimeTo>{END_DATE}T23:59:59.999Z</StartTimeTo>
  <IncludeVariations>false</IncludeVariations>
</GetSellerListRequest>"""
            root = trading_call("GetSellerList", xml)
            
            items = root.findall(".//e:Item", namespaces=NAMESP)
            if not items:
                break
                
            for item in items:
                start_time = item.findtext("e:StartTime", "", NAMESP)
                if start_time:
                    try:
                        item_date = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ")
                        earliest = min(earliest, item_date)
                    except ValueError:
                        continue
            
            total_pages = int(root.findtext(".//e:PaginationResult/e:TotalNumberOfPages", "1", NAMESP))
            print(f"Checking page {page}/{total_pages}... Earliest so far: {earliest.strftime('%Y-%m-%d')}")
            
            if page >= total_pages:
                break
            page += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
            
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
    
    print(f"\nEarliest listing found: {earliest.strftime('%Y-%m-%d')}")
    print(f"Suggested START_DATE setting: {earliest.strftime('%Y-%m-01')}")
    return earliest

# Uncomment the next line to find your earliest listing date:
# find_earliest_listing()

# API & pacing
ENTRIES_PER_PAGE = 100         # up to ~200 on many calls
SLEEP_BETWEEN_CALLS = 0.6      # seconds between pages
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_RETRIES = 3
COMPAT_LEVEL = "967"

# Output
OUT_DIR = Path("out_all")
CSV_PATH = OUT_DIR / "image_urls.csv"
IMAGES_DIR = OUT_DIR / "images_by_sku"
OUT_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Toggle downloads: set to False to only build the CSV quickly
DOWNLOAD_IMAGES = True
# ========= END CONFIG =========

TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
NAMESP = {"e": "urn:ebay:apis:eBLBaseComponents"}

def month_windows(start_date_str, end_date_str):
    """Yield (start_iso, end_iso) monthly ISO windows inclusive."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end = datetime.strptime(end_date_str, "%Y-%m-%d")
    cur = datetime(start.year, start.month, 1)
    while cur <= end:
        nxt = cur + relativedelta(months=1)
        yield (
            cur.strftime("%Y-%m-%dT00:00:00.000Z"),
            (nxt - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )
        cur = nxt

def sanitize(name: str) -> str:
    name = (name or "").strip() or "NO_SKU"
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", "+"))[:200]

def trading_call(call_name: str, xml_body: str) -> ET.Element:
    # Get a fresh/valid token each call (auto-refresh via ebay_auth)
    token = ensure_access_token()
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT_LEVEL,
        "X-EBAY-API-IAF-TOKEN": token,
    }
    r = requests.post(TRADING_ENDPOINT, data=xml_body.encode("utf-8"), headers=headers, timeout=90)
    # Retry once on token issues
    if r.status_code == 401 or "Invalid IAF token" in r.text:
        token = ensure_access_token()  # will refresh if needed
        headers["X-EBAY-API-IAF-TOKEN"] = token
        r = requests.post(TRADING_ENDPOINT, data=xml_body.encode("utf-8"), headers=headers, timeout=90)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    ack = root.findtext("e:Ack", namespaces=NAMESP)
    if ack not in ("Success", "Warning"):
        errs = root.findall(".//e:Errors", namespaces=NAMESP)
        details = "; ".join(
            f"{e.findtext('e:SeverityCode','',NAMESP)} {e.findtext('e:ShortMessage','',NAMESP)} {e.findtext('e:LongMessage','',NAMESP)}"
            for e in errs
        )
        raise RuntimeError(f"{call_name} Ack={ack}. {details or 'Unknown error.'}")
    return root

def get_seller_list_page(page: int, window_type: str, start_iso: str, end_iso: str) -> ET.Element:
    # window_type in {"StartTime","EndTime","ModTime"}
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
  {"<ModTimeFrom>" + start_iso + "</ModTimeFrom><ModTimeTo>" + end_iso + "</ModTimeTo>" if window_type == "ModTime" else ""}
  <IncludeVariations>true</IncludeVariations>
</GetSellerListRequest>"""
    return trading_call("GetSellerList", xml)

def iter_items(root: ET.Element):
    """Yield (ItemID, SKU, [image_urls])."""
    for item in root.findall(".//e:Item", namespaces=NAMESP):
        item_id = item.findtext("e:ItemID", "", NAMESP)
        sku = item.findtext("e:SKU", "", NAMESP)
        urls = [u.text for u in item.findall(".//e:PictureDetails/e:PictureURL", namespaces=NAMESP) if u.text]
        gal = item.findtext(".//e:GalleryURL", "", NAMESP)
        if gal:
            urls.append(gal)
        # de-dup preserve order
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
    """
    window_type: 'StartTime' | 'EndTime' | 'ModTime'
    seen_ids: set of ItemIDs to avoid duplicate work across passes/windows
    counters: dict to accumulate totals
    """
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

        batch = []
        items_this_page = 0

        for item_id, sku, urls in iter_items(root):
            if not item_id:
                continue
            if item_id in seen_ids and not urls:
                continue  # seen and nothing new
            seen_ids.add(item_id)
            items_this_page += 1
            counters["items"] += 1

            # CSV rows
            for u in urls:
                batch.append({
                    "item_id": item_id,
                    "sku": sku,
                    "image_url": u,
                    "source": window_type,
                    "window_start": start_iso,
                    "window_end": end_iso
                })

            # Downloads
            if DOWNLOAD_IMAGES and urls:
                label = sanitize(sku or item_id)
                folder = IMAGES_DIR / label
                folder.mkdir(parents=True, exist_ok=True)
                for i, u in enumerate(urls, start=1):
                    fname = f"{label}.jpg" if len(urls) == 1 else f"{label}_{i}.jpg"
                    dest = folder / fname
                    if dest.exists():
                        continue
                    if download_image(u, dest):
                        counters["images"] += 1
                    time.sleep(0.2)

        append_rows(batch)
        print(f"{window_type} Page {page}/{total_pages} → items:{items_this_page}, images_dl_so_far:{counters['images']}")
        page += 1
        time.sleep(SLEEP_BETWEEN_CALLS)
        if page > total_pages:
            break

def get_all_items(seen_ids: set, counters: dict):
    """Initial pass: Get ALL items regardless of date using GetMyeBaySelling."""
    print("\n=== Getting all items (including historical) ===")
    page = 1
    while True:
        try:
            xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyeBaySellingRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <ActiveList>
        <Include>true</Include>
        <Pagination>
            <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
            <PageNumber>{page}</PageNumber>
        </Pagination>
    </ActiveList>
    <SoldList>
        <Include>true</Include>
        <Pagination>
            <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
            <PageNumber>{page}</PageNumber>
        </Pagination>
    </SoldList>
    <UnsoldList>
        <Include>true</Include>
        <Pagination>
            <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
            <PageNumber>{page}</PageNumber>
        </Pagination>
    </UnsoldList>
    <DeletedFromSoldList>
        <Include>true</Include>
        <Pagination>
            <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
            <PageNumber>{page}</PageNumber>
        </Pagination>
    </DeletedFromSoldList>
    <DetailLevel>ReturnAll</DetailLevel>
</GetMyeBaySellingRequest>"""
            root = trading_call("GetMyeBaySelling", xml)
            
            items_found = 0
            for list_type in ["ActiveList", "SoldList", "UnsoldList", "DeletedFromSoldList"]:
                for item in root.findall(f".//e:{list_type}//e:Item", namespaces=NAMESP):
                    item_id = item.findtext("e:ItemID", "", NAMESP)
                    if not item_id or item_id in seen_ids:
                        continue
                    
                    sku = item.findtext("e:SKU", "", NAMESP)
                    urls = [u.text for u in item.findall(".//e:PictureDetails/e:PictureURL", namespaces=NAMESP) if u.text]
                    gal = item.findtext(".//e:GalleryURL", "", NAMESP)
                    if gal:
                        urls.append(gal)
                    
                    seen_ids.add(item_id)
                    items_found += 1
                    counters["items"] += 1
                    
                    # Save to CSV and download images
                    batch = []
                    for u in urls:
                        batch.append({
                            "item_id": item_id,
                            "sku": sku,
                            "image_url": u,
                            "source": "InitialScan",
                            "window_start": "ALL",
                            "window_end": "ALL"
                        })
                    
                    if DOWNLOAD_IMAGES and urls:
                        label = sanitize(sku or item_id)
                        folder = IMAGES_DIR / label
                        folder.mkdir(parents=True, exist_ok=True)
                        
                        skipped = 0
                        for i, u in enumerate(urls, start=1):
                            fname = f"{label}.jpg" if len(urls) == 1 else f"{label}_{i}.jpg"
                            dest = folder / fname
                            if dest.exists():
                                skipped += 1
                                continue
                            if download_image(u, dest):
                                counters["images"] += 1
                                print(f"    Downloaded: {fname}")
                            else:
                                print(f"    Failed to download: {fname}")
                            time.sleep(0.2)
                        
                        if skipped > 0:
                            print(f"    Skipped {skipped} existing images for {label}")
                    
                    append_rows(batch)
            
            print(f"Initial scan page {page} → Found {items_found} items, Total images so far: {counters['images']}")
            
            # Check if we need more pages
            has_more = False
            for list_type in ["ActiveList", "SoldList", "UnsoldList", "DeletedFromSoldList"]:
                total_pages = root.findtext(f".//e:{list_type}//e:PaginationResult/e:TotalNumberOfPages", "0", NAMESP)
                if int(total_pages) > page:
                    has_more = True
                    break
            
            if not has_more:
                break
                
            page += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
            
        except Exception as e:
            print(f"Error on initial scan page {page}: {e}")
            break

def main():
    print(f"CSV → {CSV_PATH.resolve()}")
    print(f"Images → {IMAGES_DIR.resolve()}")
    print(f"Date Range: {START_DATE} → {END_DATE}")
    counters = {"items": 0, "images": 0}
    seen_ids = set()

    # Initial pass: Get ALL historical items
    get_all_items(seen_ids, counters)

    # Pass 1: items that STARTED in each month
    for s_iso, e_iso in month_windows(START_DATE, END_DATE):
        process_window("StartTime", s_iso, e_iso, seen_ids, counters)

    # Pass 2: items that ENDED in each month (captures ended that may not appear above)
    for s_iso, e_iso in month_windows(START_DATE, END_DATE):
        process_window("EndTime", s_iso, e_iso, seen_ids, counters)

    # Pass 3: items MODIFIED in each month (catches revised items)
    for s_iso, e_iso in month_windows(START_DATE, END_DATE):
        process_window("ModTime", s_iso, e_iso, seen_ids, counters)

    print("\n==== DONE ====")
    print(f"Unique items processed: {len(seen_ids)}")
    print(f"New images downloaded: {counters['images']}")
    
    # Count total images in the backup
    total_images = 0
    for dirpath, dirnames, filenames in os.walk(IMAGES_DIR):
        total_images += len([f for f in filenames if f.endswith('.jpg')])
    print(f"Total images in backup: {total_images}")
    
    print(f"\nBackup Locations:")
    print(f"CSV file → {CSV_PATH.resolve()}")
    print(f"Images → {IMAGES_DIR.resolve()}")

if __name__ == "__main__":
    main()
