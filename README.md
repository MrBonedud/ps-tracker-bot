# ps-deal-tracker

A lightweight, serverless tracker that monitors PlayStation Store game discounts and pings you on Discord when games on your wishlist hit target prices.

> Built and vibecoded in ~2 hours because PlayStation Store sales notifications are terrible.

Runs on a scheduled GitHub Actions cron job. Instead of spinning up heavy headless browsers, it queries the PlayStation Store GraphQL endpoint directly—checking an entire watchlist in ~10 seconds with zero infrastructure costs.

---

## Why this exists

The PlayStation Store sends generic promo emails, but it doesn't let you set custom price thresholds (e.g., *"ping me only if Sekiro drops under $25"*).

Most open-source price scrapers use Playwright or Puppeteer to render the store's Single Page App (SPA). That works, but downloading a 500MB Chromium instance on every GitHub Actions run eats up minutes and takes 2+ minutes per check. This project bypasses the browser completely by querying Sony's persisted GraphQL pricing operations directly.

---

## Features

- **Blazing fast:** Checks 10+ games in ~10 seconds over plain HTTPS requests.
- **Smart price detection:** Accurately distinguishes between standard purchases and PlayStation Plus subscription tiers (PS Plus Extra/Deluxe "Included" games are filtered out).
- **All-Time Low (ATL) alerts:** Tracks historical pricing in `state.json` and flags new record lows with a dedicated banner.
- **Dynamic countdowns:** Parses promo expiration times and renders dynamic Discord countdown timestamps (e.g. *Ends in 3 days*).
- **Anti-spam logic:** Only pings when a deal starts or drops lower. When a sale ends, it resets so you get notified if the game goes on sale again later.
- **Manage from your phone:** Add games, remove games, or view your watchlist simply by opening a GitHub Issue from the mobile app.
- **Tested:** Includes an automated `pytest` test suite with CI checks on push and PR.

---

## 3-Minute Setup

### 1. Fork or clone this repo

Click **Fork** at the top right to get your own copy. Keep your fork **Private** if you want your games list and Discord activity kept private, or **Public** to share.

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

MIT
