"""
Unit tests for scripts/add_game.py
Tests issue title and body parsing, multi-game handling, duplicate detection,
remove command, list command, and ignoring unrelated issues.
"""

import json
from unittest.mock import patch

import pytest

from scripts import add_game


def test_parse_issue_ignores_unrelated_issue(tmp_path, monkeypatch):
    """Issues not containing add/track/remove/list should be ignored silently."""
    event = {
        "issue": {
            "title": "Replace PlayStation Store browser scraping with GraphQL requests #6",
            "body": "Goal: Replace current scraper",
            "url": "https://api.github.com/repos/test/issues/6",
        }
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

    with patch.object(add_game, "post_github_comment") as mock_comment, pytest.raises(SystemExit) as exc:
        add_game.parse_issue()

    assert exc.value.code == 0
    assert mock_comment.call_count == 0


def test_parse_issue_adds_single_game(tmp_path, monkeypatch):
    """Test adding a game with URL and price."""
    games_file = tmp_path / "games.json"
    games_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(add_game, "GAMES_FILE", games_file)

    event = {
        "issue": {
            "title": "add: https://store.playstation.com/en-us/product/UP0002-CUSA12047_00-SEKIROGAME000001 25",
            "body": "",
            "url": "https://api.github.com/repos/test/issues/10",
        }
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

    mock_details = {
        "product_id": "UP0002-CUSA12047_00-SEKIROGAME000001",
        "name": "Sekiro: Shadows Die Twice",
        "available": True,
        "current_price": 29.99,
    }

    with patch.object(add_game.ps_api, "get_game_price", return_value=mock_details), \
         patch.object(add_game, "post_github_comment") as mock_comment, \
         patch.object(add_game, "close_github_issue") as mock_close:
        
        add_game.parse_issue()

        updated_games = json.loads(games_file.read_text(encoding="utf-8"))
        assert len(updated_games) == 1
        assert updated_games[0]["name"] == "Sekiro: Shadows Die Twice"
        assert updated_games[0]["max_price"] == 25.0
        assert mock_comment.call_count == 1
        assert mock_close.call_count == 1


def test_parse_issue_adds_multiple_games(tmp_path, monkeypatch):
    """Test adding more than one game in a single issue."""
    games_file = tmp_path / "games.json"
    games_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(add_game, "GAMES_FILE", games_file)

    body = """
    Please track these two games:
    1. https://store.playstation.com/en-us/product/UP0082-CUSA07211_00-FFVIIREMAKE00000 20
    2. https://store.playstation.com/en-us/product/UP0177-PPSA05109_00-P5RGAME000000000 25
    """
    event = {
        "issue": {
            "title": "add multiple games",
            "body": body,
            "url": "https://api.github.com/repos/test/issues/11",
        }
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

    def mock_get_price(pid):
        if "FFVII" in pid:
            return {"name": "Final Fantasy VII Remake", "available": True}
        return {"name": "Persona 5 Royal", "available": True}

    with patch.object(add_game.ps_api, "get_game_price", side_effect=mock_get_price), \
         patch.object(add_game, "post_github_comment"), \
         patch.object(add_game, "close_github_issue"):

        add_game.parse_issue()

        updated_games = json.loads(games_file.read_text(encoding="utf-8"))
        assert len(updated_games) == 2
        names = [g["name"] for g in updated_games]
        assert "Final Fantasy VII Remake" in names
        assert "Persona 5 Royal" in names


def test_parse_issue_remove_by_name(tmp_path, monkeypatch):
    """Test removing a game by name substring."""
    games_file = tmp_path / "games.json"
    initial_games = [
        {"name": "Destiny 2", "url": "https://store.playstation.com/.../destiny", "max_price": 20.0},
        {"name": "Sekiro", "url": "https://store.playstation.com/.../sekiro", "max_price": 25.0},
    ]
    games_file.write_text(json.dumps(initial_games), encoding="utf-8")
    monkeypatch.setattr(add_game, "GAMES_FILE", games_file)

    event = {
        "issue": {
            "title": "remove: Destiny 2",
            "body": "",
            "url": "https://api.github.com/repos/test/issues/13",
        }
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

    with patch.object(add_game, "post_github_comment") as mock_comment, \
         patch.object(add_game, "close_github_issue") as mock_close:

        add_game.parse_issue()

        updated_games = json.loads(games_file.read_text(encoding="utf-8"))
        assert len(updated_games) == 1
        assert updated_games[0]["name"] == "Sekiro"
        assert mock_comment.call_count == 1
        assert mock_close.call_count == 1


def test_parse_issue_list_command(tmp_path, monkeypatch):
    """Test listing watchlist via issue."""
    games_file = tmp_path / "games.json"
    initial_games = [
        {"name": "Bloodborne", "url": "https://store.playstation.com/.../bloodborne", "max_price": 15.0}
    ]
    games_file.write_text(json.dumps(initial_games), encoding="utf-8")
    monkeypatch.setattr(add_game, "GAMES_FILE", games_file)

    event = {
        "issue": {
            "title": "list",
            "body": "",
            "url": "https://api.github.com/repos/test/issues/14",
        }
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

    with patch.object(add_game, "post_github_comment") as mock_comment, \
         patch.object(add_game, "close_github_issue") as mock_close:

        add_game.parse_issue()

        assert mock_comment.call_count == 1
        comment_arg = mock_comment.call_args[0][2]
        assert "Bloodborne" in comment_arg
        assert mock_close.call_count == 1
