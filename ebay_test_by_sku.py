#!/usr/bin/env python3
# Test downloader: Active items only (first N), filenames as <SKU>.jpg
# pip install requests

import os, time, requests, xml.etree.ElementTree as ET
from pathlib import Path

# ---------- CONFIG ----------
TOKEN_FILE = Path("token.txt")
ACCESS_TOKEN = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
if not ACCESS_TOKEN:
    raise SystemExit("⚠️  token.txt not found or empty. Please create it and paste your OAuth token inside.")

MAX_ITEMS_TO_FETCH = 5          # change to test more items
ENTRIES_PER_PAGE = 10           # items per page from eBay
COMPAT_LEVEL = "967"
TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
NAMESP = {"e": "urn:ebay:apis:eBLBaseComponents"}

OUT_DIR = Path("out_test")
IMG_DIR = OUT_DIR / "images_by_sku"
OUT_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

# ---------- UTILITIES ----------
def trading_call(call_name: str, xml_body: str) -> ET.Element:
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT_LEVEL,
        "X-EBAY-API-IAF-TOKEN": ACCESS_TOKEN,
    }
    r = requests.post(TRADING_ENDPOINT, data=xml_body.encode("utf-8"), headers=headers, timeout=90)
    r.raise_for_status()
    root = ET.fromstring(r.text)
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

def sanitize(name: str) -> str:
    name = name.strip() or "NO_SKU"
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", "+"))[:200]

def get_active_item_ids(limit: int):
    """Get up to 'limit' active ItemIDs via GetMyeBaySelling."""
    item_ids = []
    page = 1
    while len(item_ids) < limit:
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyeBaySellingRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnAll</DetailLevel>
  <ActiveList>
    <Include>true</Include>
    <Pagination>
      <EntriesPerPage>{ENTRIES_PER_PAGE}</EntriesPerPage>
      <PageNumber>{page}</PageNumber>
    </Pagination>
  </ActiveList>
</GetMyeBaySellingRequest>"""
        root = trading_call("GetMyeBaySelling", xml)
        items = root.findall(".//e:ActiveList/e:ItemArray/e:Item", namespaces=NAMESP)
        if not items:
            break
        for it in items:
            item_id = it.findtext("e:ItemID", namespaces=NAMESP)
            if item_id:
                item_ids.append(item_id)
                if len(item_ids) >= limit:
                    break
        total_pages = root.findtext(".//e:ActiveList/e:PaginationResult/e:TotalNumberOfPages", namespaces=NAMESP)
        total_pages = int(total_pages) if total_pages and total_pages.isdigit() else page
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)
    return item_ids

def get_item_details(item_id: str):
    """Return (sku, [picture_urls]) using GetItem."""
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ItemID>{item_id}</ItemID>
  <IncludeItemSpecifics>false</IncludeItemSpecifics>
  <DetailLevel>ReturnAll</DetailLevel>
</GetItemRequest>"""
    root = trading_call("GetItem", xml)
    sku = root.findtext(".//e:Item/e:SKU", namespaces=NAMESP) or ""
    urls = [n.text for n in root.findall(".//e:Item//e:PictureDetails/e:PictureURL", namespaces=NAMESP) if n.text]
    gal = root.findtext(".//e:Item//e:GalleryURL", namespaces=NAMESP)
    if gal:
        urls.append(gal)
    seen, uniq = set(), []
    for u in urls:
        if u and u not in seen:
            uniq.append(u); seen.add(u)
    return sku, uniq

def download(url: str, dest: Path):
    for attempt in range(1, 4):
        try:
            r = requests.get(url, timeout=30, allow_redirects=True)
            if r.ok and r.content:
                dest.write_bytes(r.content)
                return True
        except Exception:
            pass
        time.sleep(1.2 * attempt)
    return False

# ---------- MAIN ----------
def main():
    print("Fetching a small sample of ACTIVE items...")
    ids = get_active_item_ids(MAX_ITEMS_TO_FETCH)
    print(f"Active ItemIDs: {ids}")

    for item_id in ids:
        sku, urls = get_item_details(item_id)
        label = sanitize(sku or item_id)
        folder = IMG_DIR / label
        folder.mkdir(parents=True, exist_ok=True)
        if not urls:
            print(f"[{label}] no images")
            continue

        for i, u in enumerate(urls, start=1):
            basename = f"{label}.jpg" if len(urls) == 1 else f"{label}_{i}.jpg"
            dest = folder / basename
            if dest.exists():
                continue
            ok = download(u, dest)
            print(f"[{label}] {'OK' if ok else 'FAIL'} → {basename}")
            time.sleep(0.2)

    print(f"\n✅ Done! Check folder: {IMG_DIR.resolve()}")

if __name__ == "__main__":
    main()
