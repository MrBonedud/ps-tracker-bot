"""
Unit tests for scripts/ps_api.py
Tests URL parsing, GraphQL request handling, response parsing, and error handling.
"""

import json
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from scripts import ps_api


# ==========================================
# 1. Product ID & URL Extraction Tests
# ==========================================

def test_extract_product_id_raw_id():
    raw = "UP0002-CUSA12047_00-SEKIROGAME000001"
    assert ps_api.extract_product_id(raw) == raw


def test_extract_product_id_product_url():
    url = "https://store.playstation.com/en-us/product/UP0102-PPSA04288_00-BH20000DELUXE001"
    assert ps_api.extract_product_id(url) == "UP0102-PPSA04288_00-BH20000DELUXE001"


def test_extract_product_id_with_query_params():
    url = "https://store.playstation.com/en-us/product/UP0082-CUSA07211_00-FFVIIREMAKE00000?emcid=pa-sl-48293#details"
    assert ps_api.extract_product_id(url) == "UP0082-CUSA07211_00-FFVIIREMAKE00000"


def test_extract_product_id_concept_url():
    concept_url = "https://store.playstation.com/en-us/concept/217551"
    html_mock = """
    <html>
      <body>
        <script>var id = "UP0082-CUSA04551_00-GOTYORHADIGITAL0-U002";</script>
      </body>
    </html>
    """.encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = html_mock
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        pid = ps_api.extract_product_id(concept_url)
        assert pid == "UP0082-CUSA04551_00-GOTYORHADIGITAL0"


def test_extract_product_id_invalid():
    assert ps_api.extract_product_id("") is None
    assert ps_api.extract_product_id("https://google.com") is None
    assert ps_api.extract_product_id("not-a-product-id") is None


# ==========================================
# 2. GraphQL Response Parsing Tests
# ==========================================

def test_parse_graphql_response_regular_price():
    mock_data = {
        "data": {
            "productRetrieve": {
                "id": "UP0002-CUSA12047_00-TEST000001",
                "name": "Cool Game™",
                "webctas": [
                    {
                        "type": "ADD_TO_CART",
                        "meta": {"upSellService": "NONE"},
                        "price": {
                            "applicability": "APPLICABLE",
                            "basePrice": "$59.99",
                            "basePriceValue": 5999,
                            "discountedValue": 5999,
                            "currencyCode": "USD",
                            "isTiedToSubscription": False,
                            "endTime": None,
                        },
                    }
                ],
            }
        }
    }

    res = ps_api.parse_graphql_response("UP0002-CUSA12047_00-TEST000001", mock_data)
    assert res["available"] is True
    assert res["name"] == "Cool Game"
    assert res["current_price"] == 59.99
    assert res["original_price"] == 59.99
    assert res["is_on_sale"] is False
    assert res["discount_percent"] == 0
    assert res["sale_ends_ts"] is None


def test_parse_graphql_response_discounted_sale():
    mock_data = {
        "data": {
            "productRetrieve": {
                "id": "UP0102-PPSA04288_00-BH20000DELUXE001",
                "name": "RESIDENT EVIL 2 Deluxe Edition",
                "webctas": [
                    {
                        "type": "ADD_TO_CART",
                        "meta": {"upSellService": "NONE"},
                        "price": {
                            "applicability": "APPLICABLE",
                            "basePrice": "$49.99",
                            "basePriceValue": 4999,
                            "discountedPrice": "$9.99",
                            "discountedValue": 999,
                            "currencyCode": "USD",
                            "isTiedToSubscription": False,
                            "savingTag": "Save 80%",
                            "endTime": "1796111940000",
                            "history": {
                                "lowestRecentPrice": "Lowest price in last 30 days: $49.99"
                            },
                        },
                    }
                ],
            }
        }
    }

    res = ps_api.parse_graphql_response("UP0102-PPSA04288_00-BH20000DELUXE001", mock_data)
    assert res["available"] is True
    assert res["name"] == "RESIDENT EVIL 2 Deluxe Edition"
    assert res["current_price"] == 9.99
    assert res["original_price"] == 49.99
    assert res["is_on_sale"] is True
    assert res["discount_percent"] == 80
    assert res["saving_tag"] == "Save 80%"
    assert res["sale_ends_ts"] == 1796111940
    assert res["lowest_recent_price"] == "Lowest price in last 30 days: $49.99"


def test_parse_graphql_response_skips_subscription_tier():
    mock_data = {
        "data": {
            "productRetrieve": {
                "id": "UP9000-CUSA00900_00-BLOODBORNE000000",
                "name": "Bloodborne™",
                "webctas": [
                    # Offer 0: PS Plus subscription tier
                    {
                        "type": "SUBSCRIBE",
                        "meta": {"upSellService": "PS_PLUS"},
                        "price": {
                            "basePriceValue": 1999,
                            "discountedValue": 0,
                            "isTiedToSubscription": True,
                        },
                    },
                    # Offer 1: Standard purchase
                    {
                        "type": "ADD_TO_CART",
                        "meta": {"upSellService": "NONE"},
                        "price": {
                            "applicability": "APPLICABLE",
                            "basePriceValue": 1999,
                            "discountedValue": 1999,
                            "isTiedToSubscription": False,
                        },
                    },
                ],
            }
        }
    }

    res = ps_api.parse_graphql_response("UP9000-CUSA00900_00-BLOODBORNE000000", mock_data)
    assert res["available"] is True
    assert res["current_price"] == 19.99
    assert res["is_on_sale"] is False


def test_parse_graphql_response_empty_or_unavailable():
    res = ps_api.parse_graphql_response("EMPTY-ID", {})
    assert res["available"] is False
    assert res["error"] is not None

    res_no_ctas = ps_api.parse_graphql_response("NO-CTAS", {"data": {"productRetrieve": {"name": "Test", "webctas": []}}})
    assert res_no_ctas["available"] is False


# ==========================================
# 3. Retries & Error Handling Tests
# ==========================================

def test_fetch_graphql_404_does_not_retry():
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        data = ps_api.fetch_graphql_raw("NON_EXISTENT_PRODUCT", max_retries=3)
        assert data == {}
        assert mock_url.call_count == 1  # No repeated retries for 404


def test_fetch_graphql_retries_on_500():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"data": {"productRetrieve": {"name": "Recovered"}}}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen") as mock_url, patch("time.sleep"):
        # First call fails with 500, second call succeeds
        mock_url.side_effect = [
            urllib.error.HTTPError("url", 500, "Server Error", {}, None),
            mock_resp,
        ]
        data = ps_api.fetch_graphql_raw("RETRY_PROD", max_retries=3)
        assert data["data"]["productRetrieve"]["name"] == "Recovered"
        assert mock_url.call_count == 2
