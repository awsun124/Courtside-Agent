"""Collect bounded NBA statistics snapshots separately from news rankings."""
from contextlib import closing
from datetime import timedelta
import json
import math
import sqlite3
import subprocess
from urllib.parse import urlencode

from .stories import parse_date

METRICS = ("PTS", "REB", "AST", "STL", "BLK")


def season_for(now):
    year = now.year if now.month >= 10 else now.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def source_url(kind, season):
    if kind == "teams":
        return "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?" + urlencode(dict(season=int(season[:4]) + 1, seasontype=2))
    endpoint = "leagueleaders" if kind == "players" else "leaguestandingsv3"
    params = dict(LeagueID="00", Season=season, SeasonType="Regular Season")
    if kind == "players":
        params.update(PerMode="PerGame", Scope="S", StatCategory="PTS", ActiveFlag="")
    return "https://stats.nba.com/stats/" + endpoint + "?" + urlencode(params)


def fetch_stats(url):
    result = subprocess.run([
        "curl", "--disable", "--silent", "--max-time", "15", "--connect-timeout", "8",
        "--max-filesize", "3000000", "--proto", "=https", "--header", "Referer: https://www.espn.com/" if "espn.com/" in url else "Referer: https://www.nba.com/",
        "--header", "User-Agent: CourtSide/0.1 (cached statistics)", "--write-out", "\n%{http_code}", url,
    ], capture_output=True, text=True, timeout=18)
    body, _, status = result.stdout.rpartition("\n")
    if result.returncode or status != "200":
        raise ValueError("Statistics source did not respond successfully")
    try:
        return json.loads(body)
    except ValueError:
        raise ValueError("Statistics source returned unusable data") from None


def rows_from(payload, season):
    if not isinstance(payload, dict):
        raise ValueError("Invalid NBA statistics response")
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict) or parameters.get("Season") != season:
        raise ValueError("NBA statistics response has a different season")
    datasets = payload.get("resultSets", payload.get("resultSet", []))
    if isinstance(datasets, dict):
        datasets = [datasets]
    if not isinstance(datasets, list) or len(datasets) != 1:
        raise ValueError("Expected one NBA statistics dataset")
    dataset = datasets[0]
    if not isinstance(dataset, dict):
        raise ValueError("Invalid statistics dataset")
    headers, rows = dataset.get("headers"), dataset.get("rowSet")
    if not isinstance(headers, list) or not headers or not all(isinstance(key, str) for key in headers) or len(set(headers)) != len(headers):
        raise ValueError("Invalid statistics columns")
    if not isinstance(rows, list) or len(rows) > 2000 or any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
        raise ValueError("Invalid statistics rows")
    return [dict(zip(headers, row)) for row in rows]


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid statistics number")
    return value


def parse_players(payload, season):
    if not isinstance(payload, dict):
        raise ValueError("Invalid player statistics response")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict) or parameters.get("PerMode") != "PerGame" or parameters.get("SeasonType") != "Regular Season":
        raise ValueError("Expected regular-season per-game statistics")
    players, ids = [], set()
    for row in rows_from(payload, season):
        player_id = int(number(row["PLAYER_ID"]))
        if player_id in ids or not isinstance(row["PLAYER"], str) or not row["PLAYER"].strip() or not isinstance(row["TEAM"], str):
            raise ValueError("Invalid or duplicate player")
        ids.add(player_id)
        players.append(dict(id=player_id, name=row["PLAYER"], team=row["TEAM"], games=int(number(row["GP"])),
                            **{key.lower(): number(row[key]) for key in METRICS}))
    if not players:
        raise ValueError("No player statistics returned")
    return players


def parse_teams(payload, season):
    year = int(season[:4]) + 1
    if not isinstance(payload, dict) or payload.get("abbreviation") != "NBA" or payload.get("season", {}).get("year") != year:
        raise ValueError("Expected the requested NBA season")
    teams, ids = [], set()
    conferences = {"Eastern Conference": "East", "Western Conference": "West"}
    children = payload.get("children")
    if not isinstance(children, list) or len(children) != 2:
        raise ValueError("Expected two conferences")
    for group in children:
        conference = conferences.get(group.get("name"))
        standings = group.get("standings", {})
        entries = standings.get("entries", [])
        if not conference or standings.get("season") != year or standings.get("seasonType") != 2 or len(entries) != 15:
            raise ValueError("Expected 15 regular-season teams in each conference")
        for entry in entries:
            team = entry["team"]
            team_id = int(team["id"])
            name = team["displayName"]
            stats = {stat["name"]: stat.get("value") for stat in entry["stats"]}
            wins, losses = number(stats["wins"]), number(stats["losses"])
            if team_id in ids or team_id <= 0 or not isinstance(name, str) or not name.strip():
                raise ValueError("Invalid or duplicate team")
            if int(wins) != wins or int(losses) != losses or wins + losses > 82:
                raise ValueError("Invalid team record")
            ids.add(team_id)
            points = number(stats["avgPointsFor"]) if stats.get("avgPointsFor") is not None else None
            allowed = number(stats["avgPointsAgainst"]) if stats.get("avgPointsAgainst") is not None else None
            teams.append(dict(id=team_id, name=name, conference=conference, wins=int(wins), losses=int(losses),
                              win_percentage=wins / (wins + losses) if wins + losses else 0,
                              points_per_game=points, points_allowed=allowed,
                              point_difference=round(points - allowed, 1) if points is not None and allowed is not None else None))
    if len(ids) != 30 or {team["conference"] for team in teams} != {"East", "West"}:
        raise ValueError("Expected 30 unique NBA teams in both conferences")
    return teams


def read_stats(database, season, now):
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute("SELECT snapshot_json FROM stats_snapshots WHERE season=?", (season,)).fetchone()
    result = json.loads(row[0]) if row else dict(season=season, source="NBA.com / ESPN", players=None, teams=None, checked_at=None)
    for kind in ("players", "teams"):
        source = result.get(kind)
        if source:
            source["stale"] = not source.get("collected_at") or (now - parse_date(source["collected_at"])) > timedelta(hours=26)
    return result


def save_stats(database, season, now, transport=fetch_stats):
    result = read_stats(database, season, now)
    result["source"] = "NBA.com / ESPN"
    for kind, parser in (("players", parse_players), ("teams", parse_teams)):
        url = source_url(kind, season)
        try:
            rows = parser(transport(url), season)
            result[kind] = dict(rows=rows, collected_at=now.isoformat(), source_url=url, source_name="NBA.com" if kind == "players" else "ESPN", error=None)
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError, subprocess.SubprocessError, OSError):
            existing = result.get(kind)
            result[kind] = {**(existing or dict(rows=[], collected_at=None, source_url=url)),
                            "error": "Statistics source unavailable. Showing saved data." if existing and existing.get("rows") else "Statistics source unavailable. No data collected."}
    result["checked_at"] = now.isoformat()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("INSERT INTO stats_snapshots VALUES (?, ?) ON CONFLICT(season) DO UPDATE SET snapshot_json=excluded.snapshot_json", (season, json.dumps(result)))
    return result


def collect_stats_daily(database, now):
    from .schedule import daily_times
    due, _ = daily_times(now)
    if now < due:
        return False
    season, slot = season_for(now), due.isoformat()
    with closing(sqlite3.connect(database)) as connection, connection:
        claimed = connection.execute("INSERT OR IGNORE INTO stats_collections VALUES (?, ?)", (slot, season)).rowcount
    if claimed:
        save_stats(database, season, now)
    return bool(claimed)
