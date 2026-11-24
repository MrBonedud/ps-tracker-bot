"""
Watchlist Manager from GitHub Issues
Handles:
  - 'add: <url> [target_price]' : adds or updates one or multiple games
  - 'remove: <game_name_or_url>' : removes a game from the watchlist
  - 'list' / 'watchlist' : comments with a formatted table of all tracked games
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# Add scripts directory to path if needed
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ps_api

REPO_ROOT = Path(__file__).resolve().parent.parent
GAMES_FILE = REPO_ROOT / "games.json"
STATE_FILE = REPO_ROOT / "state.json"
DEFAULT_MAX_PRICE = 20.0


def post_github_comment(issue_url: str, token: str, body: str):
    """Post a comment on a GitHub issue."""
    req = urllib.request.Request(
        f"{issue_url}/comments",
        data=json.dumps({"body": body}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "PS-Deal-Tracker",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        print(f"Failed to post comment: {e}")
        return False


def close_github_issue(issue_url: str, token: str):
    """Close a GitHub issue."""
    req = urllib.request.Request(
        issue_url,
        data=json.dumps({"state": "closed"}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "PS-Deal-Tracker",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Failed to close issue: {e}")
        return False


def load_games():
    if GAMES_FILE.exists():
        try:
            with open(GAMES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: could not read {GAMES_FILE}: {e}")
    return []


def save_games(games):
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2)


def handle_list(issue_url: str, token: str):
    """Handles 'list' command by posting the current watchlist table."""
    games = load_games()
    state = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    if not games:
        msg = "📋 **Your Watchlist is currently empty.**\n\nAdd games by opening an issue: `add: <store_link> [price]`."
    else:
        rows = [
            "📋 **Current PlayStation Watchlist**\n",
            "| # | Game | Target Price | Latest Price | Status |",
            "| :-: | :--- | :-: | :-: | :-: |",
        ]
        for i, g in enumerate(games, 1):
            name = g.get("name", "Unknown Game")
            url = g.get("url", "#")
            max_p = f"${float(g.get('max_price', DEFAULT_MAX_PRICE)):.2f}"
            
            # Check state for live pricing
            st = state.get(url, {})
            cur_p = f"${st.get('current_price', 0):.2f}" if "current_price" in st else "—"
            if st.get("is_on_sale"):
                status = f"🔥 **SALE (-{st.get('discount_percent', 0)}%)**"
            else:
                status = "Regular" if "current_price" in st else "Pending Check"

            link = f"[{name}]({url})" if url != "#" else name
            rows.append(f"| {i} | {link} | ≤ {max_p} | {cur_p} | {status} |")

        rows.append(f"\n*Total tracked games: {len(games)}*")
        msg = "\n".join(rows)

    if issue_url and token:
        post_github_comment(issue_url, token, msg)
        close_github_issue(issue_url, token)
    print(msg)


def handle_remove(target_str: str, issue_url: str, token: str):
    """Handles 'remove: <target>' command by deleting matches from games.json."""
    games = load_games()
    if not games:
        msg = "❌ Your watchlist is currently empty."
        if issue_url and token:
            post_github_comment(issue_url, token, msg)
            close_github_issue(issue_url, token)
        return

    target_clean = target_str.strip().strip("'\"").lower()
    target_pid = ps_api.extract_product_id(target_clean)

    retained = []
    removed = []

    for g in games:
        name_lower = g.get("name", "").lower()
        url_lower = g.get("url", "").lower()
        g_pid = ps_api.extract_product_id(g.get("url", ""))

        is_match = False
        # Match by product ID
        if target_pid and g_pid and target_pid.lower() == g_pid.lower():
            is_match = True
        # Match by URL substring
        elif target_clean in url_lower:
            is_match = True
        # Match by game name substring
        elif target_clean in name_lower or name_lower in target_clean:
            is_match = True

        if is_match:
            removed.append(g.get("name") or g.get("url"))
        else:
            retained.append(g)

    if removed:
        save_games(retained)
        removed_list = ", ".join(f"**{r}**" for r in removed)
        msg = f"🗑️ **Successfully removed from watchlist:**\n- {removed_list}\n\n*Remaining tracked games: {len(retained)}*"
        print(msg)
    else:
        msg = f"❌ Could not find **{target_str.strip()}** in your watchlist."
        print(msg)

    if issue_url and token:
        post_github_comment(issue_url, token, msg)
        close_github_issue(issue_url, token)


def handle_add(combined_text: str, title: str, is_add_command: bool, issue_url: str, token: str):
    """Handles adding or updating games from issue."""
    # Find all PlayStation URLs (both store.playstation.com and www.playstation.com)
    url_matches = list(re.finditer(r"https?://(?:store|www)\.playstation\.com/[^\s\)\>]+", combined_text))

    if not url_matches:
        if is_add_command:
            msg = (
                "❌ **Could not find a valid PlayStation link.**\n\n"
                "Please include a US PlayStation Store product link, e.g.:\n"
                "`add: https://store.playstation.com/en-us/product/... 20`"
            )
            if issue_url and token:
                post_github_comment(issue_url, token, msg)
        print("No PlayStation URLs found.")
        sys.exit(1)

    global_price_match = re.search(r"(?:max[_\s]*price|target|under|<=?|\$)\s*(\d+(?:\.\d{2})?)", combined_text, re.I)
    default_price = float(global_price_match.group(1)) if global_price_match else DEFAULT_MAX_PRICE

    games = load_games()
    actions_taken = []
    errors = []

    for match in url_matches:
        raw_url = match.group(0).split("?")[0].strip()

        following_text = combined_text[match.end(): match.end() + 50]
        local_price_match = re.search(r"^\s*(?:\$|max:?|<=?)?\s*(\d{1,3}(?:\.\d{2})?)", following_text, re.I)
        target_price = float(local_price_match.group(1)) if local_price_match else default_price

        prod_id = ps_api.extract_product_id(raw_url)
        if not prod_id:
            errors.append(f"Could not extract product ID from: `{raw_url}`")
            continue

        print(f"Validating product {prod_id}...")
        details = ps_api.get_game_price(prod_id)

        official_name = details.get("name")
        if not official_name:
            slug_match = re.search(r"/product/([A-Za-z0-9_-]+)", raw_url)
            official_name = slug_match.group(1) if slug_match else prod_id

        # Normalize URL to store format if it was a www.playstation.com link
        stored_url = raw_url
        if "www.playstation.com" in stored_url:
            stored_url = f"https://store.playstation.com/en-us/product/{prod_id}"

        existing_game = None
        for g in games:
            existing_url = g.get("url", "")
            existing_id = ps_api.extract_product_id(existing_url)
            if existing_url == stored_url or (existing_id and existing_id == prod_id):
                existing_game = g
                break

        if existing_game:
            existing_game["max_price"] = target_price
            existing_game["url"] = stored_url
            if official_name and official_name != "Unknown Game":
                existing_game["name"] = official_name
            actions_taken.append(
                f"Updated target price for **{official_name}** to **${target_price:.2f}**"
            )
        else:
            games.append({
                "name": official_name,
                "url": stored_url,
                "max_price": target_price,
            })
            actions_taken.append(
                f"Added **{official_name}** with target price **${target_price:.2f}**"
            )

    if actions_taken:
        save_games(games)
        lines = ["✅ **Watchlist Updated!**\n"]
        for act in actions_taken:
            lines.append(f"- {act}")
        if errors:
            lines.append("\n⚠️ **Warnings:**")
            for err in errors:
                lines.append(f"- {err}")
        lines.append("\n*The deal tracker will monitor these games on its next scheduled check.*")
        comment_body = "\n".join(lines)

        print("\n".join(actions_taken))
        if issue_url and token:
            post_github_comment(issue_url, token, comment_body)
            close_github_issue(issue_url, token)
    else:
        if errors and issue_url and token:
            err_body = "❌ **Could not add games from this issue:**\n\n" + "\n".join(f"- {e}" for e in errors)
            post_github_comment(issue_url, token, err_body)
        sys.exit(1)


def parse_issue():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        print("GITHUB_EVENT_PATH not set or file not found.")
        sys.exit(1)

    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)

    issue = event.get("issue", {})
    title = issue.get("title", "").strip()
    body = (issue.get("body") or "").strip()
    issue_url = issue.get("url")
    token = os.environ.get("GITHUB_TOKEN")

    combined_text = f"{title}\n{body}"

    # Route 1: LIST command
    if re.fullmatch(r"(?:list|watchlist|\/list|\/watchlist)\b.*", title, re.I):
        handle_list(issue_url, token)
        return

    # Route 2: REMOVE / DELETE command
    remove_match = re.search(r"^(?:remove|delete)[\s:](.+)$", title, re.I)
    if remove_match:
        target = remove_match.group(1).strip()
        handle_remove(target, issue_url, token)
        return

    # Route 3: ADD / TRACK command
    has_ps_url = "playstation.com" in combined_text
    is_add_command = bool(re.search(r"^(?:add|track)[\s:]", title, re.I))

    if not has_ps_url and not is_add_command:
        print(f"Issue '{title}' is not an add/remove/list request. Ignoring cleanly.")
        sys.exit(0)

    handle_add(combined_text, title, is_add_command, issue_url, token)


if __name__ == "__main__":
    parse_issue()
