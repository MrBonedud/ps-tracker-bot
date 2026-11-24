"""
PlayStation Store Deal Tracker
Checks prices for games on the US PlayStation Store via GraphQL and sends Discord notifications.
Includes Smart Deal Insights:
  - All-Time Low (ATL) tracking
  - Sale expiration countdown
  - Multi-deal rate-limit handling
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Add scripts directory to path if needed
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ps_api

REPO_ROOT = Path(__file__).resolve().parent.parent
GAMES_FILE = REPO_ROOT / "games.json"
STATE_FILE = REPO_ROOT / "state.json"
DEFAULT_MAX_PRICE = 20.0


def send_discord_notification(
    webhook_url: str,
    user_id: str | None,
    game_name: str,
    store_url: str,
    current_price: float,
    original_price: float,
    discount_percent: int,
    max_price: float,
    image_url: str | None = None,
    rating_text: str | None = None,
    expiration_ts: int | None = None,
    is_new_all_time_low: bool = False,
    previous_lowest: float | None = None,
    max_retries: int = 3,
) -> bool:
    """
    Sends an embed notification to Discord via Webhook.
    Handles Discord HTTP 429 rate limits automatically with backoff.
    """
    if not webhook_url:
        print("  [Discord] DISCORD_WEBHOOK_URL is not set. Skipping notification.")
        return False

    mention = f"<@{user_id}> " if user_id else ""
    header_tag = "🔥 **NEW ALL-TIME LOW DEAL!**" if is_new_all_time_low else "🎯 **PlayStation Deal Alert!**"
    content = f"{mention}{header_tag}"

    desc_lines = [
        f"**[{game_name}]({store_url})** is on sale for **${current_price:.2f}** (-{discount_percent}%)!"
    ]
    if is_new_all_time_low and previous_lowest:
        desc_lines.append(f"🏆 *New lowest recorded price! (Previous low: ${previous_lowest:.2f})*")

    fields = [
        {"name": "Current Price", "value": f"**${current_price:.2f}**", "inline": True},
        {"name": "Original Price", "value": f"~~${original_price:.2f}~~", "inline": True},
        {"name": "Discount", "value": f"**-{discount_percent}%**", "inline": True},
        {"name": "Target Price", "value": f"≤ ${max_price:.2f}", "inline": True},
    ]

    if rating_text:
        fields.append({"name": "Rating", "value": f"⭐ {rating_text}", "inline": True})

    if expiration_ts:
        fields.append({
            "name": "Sale Ends",
            "value": f"<t:{expiration_ts}:R> *(<t:{expiration_ts}:d>)*",
            "inline": True,
        })

    embed = {
        "title": game_name,
        "url": store_url,
        "description": "\n".join(desc_lines),
        "color": 0xFF4500 if is_new_all_time_low else 0x00439C,
        "fields": fields,
        "footer": {"text": "PS Deal Tracker • PlayStation Store (US)"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if image_url:
        embed["thumbnail"] = {"url": image_url}

    payload = {
        "content": content,
        "embeds": [embed],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "PS-Deal-Tracker/2.0",
        },
    )

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"  [Discord] Successfully sent deal alert for {game_name} (HTTP {resp.status})")
                # Add slight delay so rapid consecutive notifications don't trip Discord burst limits
                time.sleep(1.0)
                return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate limited by Discord: parse retry_after if available
                retry_after = 2.0
                try:
                    resp_body = json.loads(e.read().decode("utf-8"))
                    retry_after = float(resp_body.get("retry_after", 2.0))
                except Exception:
                    pass
                print(f"  [Discord] Rate limited (429). Retrying in {retry_after:.1f}s...")
                time.sleep(retry_after + 0.5)
            else:
                print(f"  [Discord] Failed to send webhook: HTTP {e.code} - {e.reason}")
                break
        except Exception as e:
            print(f"  [Discord] Failed to send webhook: {e}")
            break

    return False


def run_tracker():
    if not GAMES_FILE.exists():
        print(f"Error: {GAMES_FILE} does not exist.")
        sys.exit(1)

    with open(GAMES_FILE, "r", encoding="utf-8") as f:
        games = json.load(f)

    if not games:
        print("No games in watchlist. Add games to games.json.")
        return

    state = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {STATE_FILE}: {e}")

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    user_id = os.environ.get("DISCORD_USER_ID", "").strip() or None

    print(f"Starting PS Deal Tracker for {len(games)} game(s) via GraphQL...")

    for game in games:
        url = game.get("url")
        name = game.get("name") or "Unknown Game"
        max_price = float(game.get("max_price", DEFAULT_MAX_PRICE))
        notify_if_under_max = game.get("notify_if_under_max", False)

        if not url:
            print(f"Skipping entry without URL: {game}")
            continue

        print(f"\nChecking: {name} (Target: <= ${max_price:.2f})")
        print(f"  URL: {url}")

        try:
            details = ps_api.get_game_price(url)
        except Exception as e:
            print(f"  [Error] Exception during price check for {name}: {e}")
            continue

        if not details.get("available") or details.get("current_price") is None:
            err_msg = details.get("error") or "Pricing not available"
            print(f"  [Warning] Could not get price for {name}: {err_msg}")
            continue

        cur_price = details["current_price"]
        orig_price = details["original_price"] or cur_price
        is_sale = details["is_on_sale"]
        discount_pct = details["discount_percent"]
        display_title = details["name"] or name

        sale_tag = f"ON SALE (-{discount_pct}%)" if is_sale else "Regular price"
        print(f"  Price: ${cur_price:.2f} (Original: ${orig_price:.2f}) - {sale_tag}")
        if details.get("saving_tag"):
            print(f"  Badge: {details['saving_tag']}")
        if details.get("sale_ends_ts"):
            print(f"  Sale Ends (Unix TS): {details['sale_ends_ts']}")

        # Deal evaluation
        is_deal = (cur_price <= max_price) and (is_sale or notify_if_under_max)

        # Check notification history & All-Time Low
        game_state = state.get(url, {})
        last_notified_price = game_state.get("last_notified_price")
        lowest_seen_price = game_state.get("lowest_seen_price")

        # Check if this is a new All-Time Low
        is_new_all_time_low = False
        if lowest_seen_price is not None and cur_price < lowest_seen_price:
            is_new_all_time_low = True
            print(f"  🔥 NEW ALL-TIME LOW! (Current: ${cur_price:.2f} < Previous Low: ${lowest_seen_price:.2f})")

        # Notification criteria:
        # 1. Is an active deal
        # 2. Never notified before, OR price dropped lower than last notification
        should_notify = is_deal and (last_notified_price is None or cur_price < last_notified_price)

        if should_notify:
            print(f"  >>> DEAL DETECTED! Sending Discord alert for {display_title}...")
            success = send_discord_notification(
                webhook_url=webhook_url,
                user_id=user_id,
                game_name=display_title,
                store_url=url,
                current_price=cur_price,
                original_price=orig_price,
                discount_percent=discount_pct,
                max_price=max_price,
                expiration_ts=details.get("sale_ends_ts"),
                is_new_all_time_low=is_new_all_time_low,
                previous_lowest=lowest_seen_price,
            )
            if success:
                game_state["last_notified_price"] = cur_price
                game_state["last_notified_at"] = datetime.now(timezone.utc).isoformat()
        else:
            if is_deal:
                print(f"  Already notified at ${last_notified_price:.2f}. Skipping repeat ping.")
            else:
                print(f"  Not a qualifying deal (Target: <= ${max_price:.2f}, On Sale: {is_sale}).")

            # If sale ended, reset notification state so next sale triggers again
            if not is_sale and last_notified_price is not None:
                print(f"  Sale ended. Resetting notification history for next discount.")
                game_state["last_notified_price"] = None

        # Update lowest recorded price
        new_lowest = min(lowest_seen_price, cur_price) if lowest_seen_price is not None else cur_price
        game_state["lowest_seen_price"] = new_lowest

        # Update state entry
        game_state.update({
            "name": display_title,
            "product_id": details.get("product_id"),
            "current_price": cur_price,
            "original_price": orig_price,
            "discount_percent": discount_pct,
            "is_on_sale": is_sale,
            "sale_ends_ts": details.get("sale_ends_ts"),
            "last_checked": datetime.now(timezone.utc).isoformat(),
        })
        state[url] = game_state

    # Save updated state
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    print("\nTracker run complete. State saved to state.json.")


if __name__ == "__main__":
    run_tracker()
