"""
PlayStation Store GraphQL API Module
Fetches game information, pricing, and availability directly from the PlayStation Store GraphQL endpoint.
No browser or Playwright required.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPHQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"
PERSISTED_HASH_CTAS_WITH_PRICE = "911a43f47dbbf7b2f3d513d6237dedfd679e57af3f34787667a22ecad6a249cd"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://store.playstation.com",
    "Referer": "https://store.playstation.com/",
    "x-psn-store-locale-override": "en-US",
}


def extract_product_id(url_or_id: str, timeout: int = 15) -> str | None:
    """
    Extracts the PlayStation Store product ID from a string, /product/ URL, /concept/ URL,
    or a www.playstation.com/games/... game page URL.
    Returns product ID (e.g. 'UP0002-CUSA12047_00-SEKIROGAME000001') or None.
    """
    if not url_or_id:
        return None

    cleaned = url_or_id.strip().rstrip("/\\")

    # Case 1: Raw product ID: e.g. UP0002-CUSA12047_00-SEKIROGAME000001 or JP0177-PPSA31333_00-MAINGAME000000NA
    id_pattern = r"^[A-Z]{2}\d{4}-[A-Z0-9_-]{10,}$"
    if re.match(id_pattern, cleaned):
        return cleaned

    # Case 2: Standard product URL: .../product/UP0002-CUSA12047_00-SEKIROGAME000001
    prod_match = re.search(r"/product/([A-Za-z0-9_-]+)", cleaned)
    if prod_match:
        cand = prod_match.group(1)
        if re.match(r"^[A-Z]{2}\d{4}-", cand):
            return cand

    # Case 3: Concept URL: .../concept/217551
    concept_match = re.search(r"/concept/(\d+)", cleaned)
    if concept_match:
        try:
            req = urllib.request.Request(cleaned, headers={"User-Agent": HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                matches = re.findall(r"[A-Z]{2}\d{4}-[A-Z0-9_]{5,}-[A-Z0-9_]+", html)
                if matches:
                    for m in matches:
                        base_id = m.split("-U")[0]
                        if len(base_id) >= 20:
                            return base_id
                    return matches[0].split("-U")[0]
        except Exception as e:
            print(f"  [ps_api] Warning: could not resolve concept URL {cleaned}: {e}")

    # Case 4: General PlayStation game page: www.playstation.com/en-us/games/...
    if "playstation.com" in cleaned and "/games/" in cleaned:
        try:
            req = urllib.request.Request(cleaned, headers={"User-Agent": HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                store_links = re.findall(r"https?://store\.playstation\.com/[^\s\"\'\)\>]+", html)
                for sm in store_links:
                    sm_clean = sm.replace("\\", "")
                    cand_id = extract_product_id(sm_clean, timeout=timeout)
                    if cand_id:
                        return cand_id
                matches = re.findall(r"[A-Z]{2}\d{4}-[A-Z0-9_]{5,}-[A-Z0-9_]+", html)
                if matches:
                    return matches[0].split("-U")[0]
        except Exception as e:
            print(f"  [ps_api] Warning: could not resolve game page URL {cleaned}: {e}")

    # Fallback search for any product ID format in string
    generic_match = re.search(r"[A-Z]{2}\d{4}-[A-Z0-9_-]{10,}", cleaned)
    if generic_match:
        return generic_match.group(0)

    return None


def fetch_graphql_raw(product_id: str, timeout: int = 15, max_retries: int = 3) -> dict:
    """
    Calls the PlayStation Store GraphQL endpoint for productRetrieveForCtasWithPrice.
    Implements retries with exponential backoff on transient errors (429, 5xx, timeouts).
    """
    variables = {"productId": product_id}
    extensions = {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": PERSISTED_HASH_CTAS_WITH_PRICE,
        }
    }
    params = urllib.parse.urlencode({
        "operationName": "productRetrieveForCtasWithPrice",
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": json.dumps(extensions, separators=(",", ":")),
    })
    url = f"{GRAPHQL_URL}?{params}"
    req = urllib.request.Request(url, headers=HEADERS)

    last_error = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (400, 404):
                print(f"  [ps_api] Product {product_id} returned HTTP {e.code}: Not Found.")
                return {}
            if attempt < max_retries - 1:
                sleep_time = (2 ** attempt)
                print(f"  [ps_api] HTTP {e.code} for {product_id}. Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                print(f"  [ps_api] HTTP {e.code} for {product_id} after {max_retries} attempts.")
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt < max_retries - 1:
                sleep_time = (2 ** attempt)
                print(f"  [ps_api] Network/Timeout error for {product_id}. Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                print(f"  [ps_api] Network error for {product_id} after {max_retries} attempts: {e}")
        except Exception as e:
            last_error = e
            print(f"  [ps_api] Unexpected error fetching {product_id}: {e}")
            break

    return {}


def parse_graphql_response(product_id: str, data: dict) -> dict:
    """
    Parses the raw GraphQL response dict into clean product and pricing details.
    """
    result = {
        "product_id": product_id,
        "name": None,
        "available": False,
        "current_price": None,
        "original_price": None,
        "discount_percent": 0,
        "is_on_sale": False,
        "saving_tag": None,
        "sale_ends_ts": None,
        "lowest_recent_price": None,
        "currency": "USD",
        "error": None,
    }

    if not data or "data" not in data or not data["data"]:
        result["error"] = "Empty or invalid response from PlayStation Store API"
        return result

    prod = data["data"].get("productRetrieve")
    if not prod:
        result["error"] = "Product not found"
        return result

    raw_name = prod.get("name") or prod.get("invariantName") or ""
    result["name"] = raw_name.replace("™", "").replace("®", "").strip()

    webctas = prod.get("webctas") or []
    if not webctas:
        result["error"] = "No purchase CTAs found (product may be unavailable or unpurchasable)"
        return result

    standard_price_info = None

    for cta in webctas:
        price_obj = cta.get("price") or {}
        meta_obj = cta.get("meta") or {}

        if price_obj.get("isTiedToSubscription", False):
            continue
        if meta_obj.get("upSellService") and meta_obj.get("upSellService") != "NONE":
            continue

        applicability = price_obj.get("applicability")
        if applicability and applicability != "APPLICABLE":
            continue

        base_val = price_obj.get("basePriceValue")
        if base_val is not None:
            standard_price_info = price_obj
            break

    if not standard_price_info:
        for cta in webctas:
            price_obj = cta.get("price") or {}
            if price_obj.get("basePriceValue") is not None:
                standard_price_info = price_obj
                break

    if not standard_price_info:
        result["error"] = "No valid price information in product CTAs"
        return result

    base_val = standard_price_info.get("basePriceValue")
    disc_val = standard_price_info.get("discountedValue")

    base_price = float(base_val) / 100.0 if base_val is not None else None
    current_price = float(disc_val) / 100.0 if disc_val is not None else base_price

    result["available"] = True
    result["original_price"] = base_price
    result["current_price"] = current_price
    result["currency"] = standard_price_info.get("currencyCode", "USD")

    if base_price and current_price and base_price > current_price:
        result["is_on_sale"] = True
        result["discount_percent"] = round((1.0 - (current_price / base_price)) * 100)
    else:
        result["is_on_sale"] = False
        result["discount_percent"] = 0

    result["saving_tag"] = standard_price_info.get("savingTag")

    end_time_ms = standard_price_info.get("endTime")
    if end_time_ms:
        try:
            result["sale_ends_ts"] = int(end_time_ms) // 1000
        except (ValueError, TypeError):
            result["sale_ends_ts"] = None

    history = standard_price_info.get("history") or {}
    result["lowest_recent_price"] = history.get("lowestRecentPrice")

    return result


def get_game_price(product_id_or_url: str, timeout: int = 15, max_retries: int = 3) -> dict:
    """
    Main function to get game pricing and info for a PlayStation Store product.
    Accepts a product ID, a /product/ URL, a /concept/ URL, or a www.playstation.com game page URL.
    """
    pid = extract_product_id(product_id_or_url, timeout=timeout)
    if not pid:
        return {
            "product_id": None,
            "name": None,
            "available": False,
            "current_price": None,
            "original_price": None,
            "discount_percent": 0,
            "is_on_sale": False,
            "error": f"Invalid PlayStation Store product ID or URL: {product_id_or_url}",
        }

    raw_data = fetch_graphql_raw(pid, timeout=timeout, max_retries=max_retries)
    return parse_graphql_response(pid, raw_data)
