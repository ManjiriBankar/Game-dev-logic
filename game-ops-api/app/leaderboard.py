"""
leaderboard.py
Builds global and region-wise leaderboards.

Ranking rules:
  1. Higher score → better rank.
  2. Tie on score → fewer deaths wins.
  3. Tie on score + deaths → more kills wins.
  4. Flagged (suspicious) players are excluded from ranking but shown separately.
"""

from typing import List, Dict, Any
from app.data_loader import PlayerMatch
from app.suspicious import get_flagged_player_ids


def _aggregate(matches: List[PlayerMatch]) -> Dict[str, Dict]:
    """Aggregate all matches per player (sum scores, kills, deaths)."""
    players: Dict[str, Dict] = {}
    for m in matches:
        if m.player_id not in players:
            players[m.player_id] = {
                "player_id": m.player_id,
                "region": m.region,
                "device": m.device,
                "total_score": 0,
                "total_kills": 0,
                "total_deaths": 0,
                "matches_played": 0,
            }
        players[m.player_id]["total_score"] += m.score
        players[m.player_id]["total_kills"] += m.kills
        players[m.player_id]["total_deaths"] += m.deaths
        players[m.player_id]["matches_played"] += 1
    return players


def _sort_players(player_list: List[Dict]) -> List[Dict]:
    """Sort by score DESC, deaths ASC, kills DESC."""
    return sorted(
        player_list,
        key=lambda p: (-p["total_score"], p["total_deaths"], -p["total_kills"]),
    )


def get_global_leaderboard(matches: List[PlayerMatch]) -> Dict[str, Any]:
    """Return ranked global leaderboard, separating flagged players."""
    flagged_ids = get_flagged_player_ids(matches)
    aggregated = _aggregate(matches)

    clean = [p for pid, p in aggregated.items() if pid not in flagged_ids]
    flagged = [p for pid, p in aggregated.items() if pid in flagged_ids]

    ranked = _sort_players(clean)
    for i, entry in enumerate(ranked, start=1):
        entry["rank"] = i

    return {
        "leaderboard": ranked,
        "flagged_players_excluded": flagged,
        "total_ranked": len(ranked),
        "total_flagged": len(flagged),
    }


def get_region_leaderboard(matches: List[PlayerMatch]) -> Dict[str, Any]:
    """Return per-region ranked leaderboards."""
    flagged_ids = get_flagged_player_ids(matches)
    aggregated = _aggregate(matches)

    regions: Dict[str, List[Dict]] = {}
    for pid, player in aggregated.items():
        if pid in flagged_ids:
            continue
        region = player["region"]
        regions.setdefault(region, []).append(player)

    result = {}
    for region, players in regions.items():
        ranked = _sort_players(players)
        for i, entry in enumerate(ranked, start=1):
            entry["regional_rank"] = i
        result[region] = ranked

    return {"region_leaderboards": result}
