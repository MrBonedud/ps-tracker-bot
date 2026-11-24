# ps-deal-tracker

[![CI](https://github.com/MrBonedud/ps-tracker-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBonedud/ps-tracker-bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Vibecoded](https://img.shields.io/badge/status-vibecoded%20in%202h-ff69b4.svg)](#)

A lightweight, serverless tracker that monitors PlayStation Store game discounts and pings you on Discord when games on your wishlist hit target prices.

> Built and vibecoded in ~2 hours because PlayStation Store sales notifications are terrible.

Runs on a scheduled GitHub Actions cron job. Instead of spinning up heavy headless browsers, it queries the PlayStation Store GraphQL endpoint directly—checking an entire watchlist in ~10 seconds with zero infrastructure costs.

---

## Why this exists

The official PlayStation Store's wishlist situation is a comedy of errors:

1. **The Great 2020 Deletion:** When Sony redesigned the web store for the PS5 launch, they famously deleted the entire wishlist feature overnight, wiping out millions of players' saved wishlists with zero warning.
2. **The Hidden Return:** When they finally quietly brought a wishlist heart icon back in 2021, they hid it so well half the userbase still has no idea it exists—and if your list gets over ~100 games, the page famously glitches or turns blank.
3. **Useless Generic Alerts:** Even if you use it, Sony only sends vague push alerts saying *"An item on your wishlist is on sale!"*—with zero price details, no All-Time Low detection, and no custom price thresholds (e.g. *"ping me only if Sekiro drops under $25, not when a $120 deluxe bundle gets $1.50 off"*).

Most open-source price scrapers try to fix this by downloading a 500MB Chromium/Playwright browser on every single run to render the store's Single Page App (SPA). That works, but it takes minutes and chews through GitHub Actions quotas.

This project bypasses the browser completely by querying Sony's persisted GraphQL pricing operations directly—checking an entire watchlist in ~10 seconds with zero infrastructure costs.

---

## Features

- **Blazing fast:** Checks 10+ games in ~10 seconds over plain HTTPS requests.
- **Smart price detection:** Accurately distinguishes between standard purchases and PlayStation Plus subscription tiers (PS Plus Extra/Deluxe "Included" games are filtered out).
- **All-Time Low (ATL) alerts:** Tracks historical pricing in `state.json` and flags new record lows with a dedicated banner.
- **Dynamic countdowns:** Parses promo expiration times and renders dynamic Discord countdown timestamps (e.g. *Ends in 3 days*).
- **Anti-spam logic:** Only pings when a deal starts or drops lower. When a sale ends, it resets so you get notified if the game goes on sale again later.
- **Manage from your phone:** Add games, remove games, or view your watchlist simply by opening a GitHub Issue from the mobile app.
- **US Store by default:** Tracks the US PlayStation Store (`en-US`). If you pay in Euros, Yen, or GBP, you get American freedom units. Support for other regions is just an override header away in `scripts/ps_api.py`.
- **Tested:** Includes an automated `pytest` test suite with CI checks on push and PR.

### What the alert looks like in Discord

> 🔔 **DEAL ALERT: Bloodborne**
> 
> 💰 **Current Price:** ~~$19.99~~ **$9.99** `(-50% OFF)`  
> 🎯 **Target Price:** $15.00  
> ⭐ **Rating:** ★ 4.72 / 5 (52,431 ratings)  
> ⏳ **Sale Ends:** in 3 days *(dynamic Discord timestamp)*  
> 🔥 **NEW ALL-TIME LOW!** *(Cheapest price recorded since tracking started)*  
> 🔗 [View on PlayStation Store](https://store.playstation.com/en-us/product/UP9000-CUSA00900_00-BLOODBORNE000000)

---

## 3-Minute Setup

### 1. Fork or clone this repo

Click **Fork** at the top right to get your own copy. Keep your fork **Private** if you want your games list and Discord activity kept private, or **Public** to share.

> [!WARNING]
> **DO NOT try to add your wishlist games to this repo's `main` branch.**  
> 1. It literally will not work—branch protection is locked down and direct pushes are blocked.  
> 2. If you open a Pull Request trying to sneak your personal backlog onto my tracker, I *will* playfully roast you in the review comments before closing it with extreme prejudice.  
> 
> **Fork the repo** and run your tracker on your own copy! That's literally the entire point of open source.

### 2. Create a Discord Webhook

1. In your Discord server, open **Channel Settings** &rarr; **Integrations** &rarr; **Webhooks**.
2. Click **New Webhook**, name it (e.g. `PS Deals`), and copy the Webhook URL.
3. *(Optional for push pings)* Turn on **Developer Mode** in Discord (User Settings &rarr; Advanced &rarr; Developer Mode). Right-click your profile and select **Copy User ID**.

### 3. Add GitHub Secrets

In your GitHub repository, go to **Settings** &rarr; **Secrets and variables** &rarr; **Actions** and add:

| Secret Name | Value | Description |
| :--- | :--- | :--- |
| `DISCORD_WEBHOOK_URL` | `https://discord.com/api/webhooks/...` | Your Discord webhook endpoint. |
| `DISCORD_USER_ID` | `123456789012345678` | *(Optional)* Your Discord ID to ping you directly. |

### 4. Enable Workflows (Don't skip this!)

GitHub automatically disables Actions on forked repositories by default so people don't accidentally mine crypto on their servers:

1. Go to your fork's **Actions** tab.
2. Click the big green button: **"I understand my workflows, go ahead and enable them"**.
3. Select **PlayStation Deal Tracker** on the left &rarr; **Run workflow** to test your Discord webhook immediately and make sure you didn't botch the secret names.

---

## Managing Your Watchlist

You can manage your watchlist by editing `games.json` directly, or on the go via **GitHub Issues**:

### Option A: From your phone (GitHub Issues)

Just open an issue in your repo—the action processes your command, updates `games.json`, and automatically closes the issue.

- **Add a game:**  
  Title: `add: https://store.playstation.com/en-us/product/... 20`  
  *(Works with `/product/` links, `/concept/` links, and `playstation.com/.../games/...` links. Target price defaults to $20 if omitted).*
- **Add multiple games at once:**  
  Title: `add:`  
  Body: paste multiple PlayStation links with optional target prices.
- **Remove a game:**  
  Title: `remove: Bloodborne` (or by URL)
- **View your watchlist:**  
  Title: `list` (returns a formatted markdown table with live prices and sale statuses).

### Option B: Direct `games.json`

Edit `games.json` in the root of the repository:

```json
[
  {
    "name": "Bloodborne",
    "url": "https://store.playstation.com/en-us/product/UP9000-CUSA00900_00-BLOODBORNE000000",
    "max_price": 15.0
  },
  {
    "name": "Resident Evil 2 Deluxe Edition",
    "url": "https://store.playstation.com/en-us/product/UP0102-PPSA04288_00-BH20000DELUXE001",
    "max_price": 10.0
  }
]
```

---

## Workflows & Schedule

- **`tracker.yml`:** Runs automatically every 6 hours (`0 */6 * * *`). You can also click **Run workflow** in the Actions tab to trigger an instant check anytime.
- **`add-game.yml`:** Triggers when an issue starting with `add:`, `remove:`, or `list` is opened.
- **`ci.yml`:** Runs the test suite on every pull request or push.

---

## Local Development & Testing

Python 3.10+ required. Core scripts use the Python standard library only.

```bash
# Install test runner
pip install -r requirements-dev.txt

# Run the test suite
pytest -v

# Run tracker locally
python scripts/tracker.py
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Disclaimer

This project is an unofficial, independent open-source utility and is not affiliated with, endorsed by, or associated with Sony Interactive Entertainment Inc. PlayStation, PS5, PS4, and PSN are registered trademarks of Sony Interactive Entertainment Inc.

> **Please don't sue me, Sony:** I am literally building free tools that convince people to buy games on your store. If anything, you're welcome.


