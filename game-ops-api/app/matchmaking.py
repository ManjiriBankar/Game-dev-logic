"""
matchmaking.py
Skill-based matchmaking with region and ping constraints.

Algorithm:
  Step 1 – Exclude flagged players entirely.
  Step 2 – Compute a skill score per player:
             skill = total_score / matches_played   (avg score per match)
  Step 3 – Group players by region first (preferred).
  Step 4 – Within a region, split into ping tiers:
             Low  ping  ≤ 80 ms
             Mid  ping  81–150 ms
             High ping  > 150 ms
  Step 5 – Within each (region, ping_tier) bucket, sort by skill score
            and pack into groups of GROUP_SIZE (default 4).
  Step 6 – Any leftover players that cannot fill a full group are
            placed in a "partial" group (still playable, just noted).
"""

from typing import List, Dict, Any
from app.data_loader import PlayerMatch
from app.suspicious import get_flagged_player_ids

GROUP_SIZE = 4  # players per match group

PING_LOW = 80
PING_MID = 150


def _ping_tier(ping: int) -> str:
    if ping <= PING_LOW:
        return "low"
    if ping <= PING_MID:
        return "mid"
    return "high"


def _aggregate_players(matches: List[PlayerMatch]) -> Dict[str, Dict]:
    players: Dict[str, Dict] = {}
    for m in matches:
        if m.player_id not in players:
            players[m.player_id] = {
                "player_id": m.player_id,
                "region": m.region,
                "device": m.device,
                "ping": m.ping,
                "total_score": 0,
                "matches_played": 0,
            }
        players[m.player_id]["total_score"] += m.score
        players[m.player_id]["matches_played"] += 1
        # use latest ping reading
        players[m.player_id]["ping"] = m.ping
    return players


def suggest_matchmaking(matches: List[PlayerMatch]) -> Dict[str, Any]:
    """Return suggested match groups."""
    flagged_ids = get_flagged_player_ids(matches)
    aggregated = _aggregate_players(matches)

    # Only clean players participate
    clean_players = [
        p for pid, p in aggregated.items() if pid not in flagged_ids
    ]

    # Compute skill score and ping tier
    for p in clean_players:
        p["avg_score"] = p["total_score"] / max(p["matches_played"], 1)
        p["ping_tier"] = _ping_tier(p["ping"])

    # Bucket: {region: {ping_tier: [players]}}
    buckets: Dict[str, Dict[str, List]] = {}
    for p in clean_players:
        buckets.setdefault(p["region"], {}).setdefault(p["ping_tier"], []).append(p)

    groups: List[Dict[str, Any]] = []
    group_counter = 1

    for region, tiers in buckets.items():
        for tier, players in tiers.items():
            # Sort by skill score
            players.sort(key=lambda x: x["avg_score"], reverse=True)

            for i in range(0, len(players), GROUP_SIZE):
                chunk = players[i : i + GROUP_SIZE]
                groups.append(
                    {
                        "group_id": f"GRP-{group_counter:03d}",
                        "region": region,
                        "ping_tier": tier,
                        "status": "full" if len(chunk) == GROUP_SIZE else "partial",
                        "player_count": len(chunk),
                        "players": [
                            {
                                "player_id": pl["player_id"],
                                "avg_score": round(pl["avg_score"], 1),
                                "ping": pl["ping"],
                                "device": pl["device"],
                            }
                            for pl in chunk
                        ],
                    }
                )
                group_counter += 1

    return {
        "total_groups": len(groups),
        "group_size_target": GROUP_SIZE,
        "flagged_players_excluded": list(flagged_ids),
        "groups": groups,
    }
