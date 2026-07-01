"""
data_loader.py
Loads and validates match data from CSV into a list of PlayerMatch objects.
"""

import csv
import os
from dataclasses import dataclass
from typing import List

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "matches.csv")


@dataclass
class PlayerMatch:
    player_id: str
    match_id: str
    region: str
    device: str
    ping: int
    score: int
    kills: int
    deaths: int
    match_duration_seconds: int


def load_matches(path: str = DATA_PATH) -> List[PlayerMatch]:
    """Read CSV and return a list of PlayerMatch dataclass instances."""
    matches = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            matches.append(
                PlayerMatch(
                    player_id=row["player_id"].strip(),
                    match_id=row["match_id"].strip(),
                    region=row["region"].strip(),
                    device=row["device"].strip(),
                    ping=int(row["ping"]),
                    score=int(row["score"]),
                    kills=int(row["kills"]),
                    deaths=int(row["deaths"]),
                    match_duration_seconds=int(row["match_duration_seconds"]),
                )
            )
    return matches
