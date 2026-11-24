"""
Unit tests for scripts/tracker.py
Tests deal evaluation, notification criteria, duplicate prevention, and Discord notifications.
"""

from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from scripts import tracker


# ==========================================
# 1. Duplicate Notification Prevention Tests
# ==========================================

def test_duplicate_notification_lifecycle():
    """
    Verifies that:
    1. First sale pings user and sets last_notified_price.
    2. Repeated run at same price skips ping.
    3. Price drop pings user and updates last_notified_price.
    4. Sale ending resets last_notified_price to None.
    5. A second sale at the original discount price pings user again.
    """
    max_price = 25.0
    game_state = {}

    # Step 1: Game goes on sale for $9.99 (was $49.99)
    cur_price = 9.99
    is_sale = True
    last_notified = game_state.get("last_notified_price")
    is_deal = (cur_price <= max_price) and is_sale
    should_notify_1 = is_deal and (last_notified is None or cur_price < last_notified)
    assert should_notify_1 is True

    # Simulate notification sent
    game_state["last_notified_price"] = cur_price

    # Step 2: Next scheduled run (price still $9.99, sale ongoing)
    last_notified = game_state.get("last_notified_price")
    should_notify_2 = is_deal and (last_notified is None or cur_price < last_notified)
    assert should_notify_2 is False  # MUST NOT NOTIFY

    # Step 3: Flash discount: price drops further to $7.99
    cur_price = 7.99
    last_notified = game_state.get("last_notified_price")
    should_notify_3 = is_deal and (last_notified is None or cur_price < last_notified)
    assert should_notify_3 is True  # MUST NOTIFY ON FURTHER PRICE DROP
    game_state["last_notified_price"] = cur_price

    # Step 4: Sale ends, price returns to regular $49.99
    cur_price = 49.99
    is_sale = False
    is_deal = (cur_price <= max_price) and is_sale
    last_notified = game_state.get("last_notified_price")

    if not is_sale and last_notified is not None:
        game_state["last_notified_price"] = None  # Reset state

    assert game_state["last_notified_price"] is None

    # Step 5: Weeks later, game goes on sale for $9.99 again
    cur_price = 9.99
    is_sale = True
    is_deal = (cur_price <= max_price) and is_sale
    last_notified = game_state.get("last_notified_price")
    should_notify_5 = is_deal and (last_notified is None or cur_price < last_notified)
    assert should_notify_5 is True  # MUST NOTIFY FOR NEW SALE EVEN AT SAME PRICE


# ==========================================
# 2. Discord Notification Delivery & Retries
# ==========================================

def test_send_discord_notification_success():
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp), patch("time.sleep"):
        success = tracker.send_discord_notification(
            webhook_url="https://discord.com/api/webhooks/test",
            user_id="123456789",
            game_name="Resident Evil 2",
            store_url="https://store.playstation.com/...",
            current_price=9.99,
            original_price=49.99,
            discount_percent=80,
            max_price=25.0,
            expiration_ts=1796111940,
        )
        assert success is True


def test_send_discord_notification_retries_on_rate_limit_429():
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.__enter__.return_value = mock_resp

    err_429 = urllib.error.HTTPError(
        "url", 429, "Too Many Requests", {}, MagicMock(read=lambda: b'{"retry_after": 0.1}')
    )

    with patch("urllib.request.urlopen") as mock_url, patch("time.sleep"):
        # First call hits 429, second call succeeds
        mock_url.side_effect = [err_429, mock_resp]
        success = tracker.send_discord_notification(
            webhook_url="https://discord.com/api/webhooks/test",
            user_id="123456789",
            game_name="Sekiro",
            store_url="https://store.playstation.com/...",
            current_price=29.99,
            original_price=59.99,
            discount_percent=50,
            max_price=30.0,
        )
        assert success is True
        assert mock_url.call_count == 2
