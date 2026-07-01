"""
main.py
FastAPI entry point — Game Ops System

Endpoints:
  POST /submit-score          – Add a new match record
  GET  /leaderboard           – Global leaderboard (flagged players excluded)
  GET  /leaderboard/region    – Per-region leaderboards
  GET  /flagged-players       – Suspicious / flagged player list
  GET  /matchmaking           – Suggested match groups
  GET  /players               – Raw list of all submitted records
  GET  /health                – Health check
"""

import csv
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.data_loader import load_matches, PlayerMatch, DATA_PATH
from app.leaderboard import get_global_leaderboard, get_region_leaderboard
from app.suspicious import detect_suspicious
from app.matchmaking import suggest_matchmaking

# ── app setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Game Ops System API",
    description=(
        "Handles player match data for a multiplayer game event. "
        "Provides leaderboard, suspicious player detection, and matchmaking."
    ),
    version="1.0.0",
)

# Serve the dashboard UI from /static; redirect / → /static/index.html
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ── helper ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    """Redirect root to the dashboard UI."""
    return RedirectResponse(url="/static/index.html")

def _get_matches() -> list[PlayerMatch]:
    """Always reload from CSV so submitted scores are reflected immediately."""
    return load_matches()


# ── request / response models ─────────────────────────────────────────────────

class MatchSubmission(BaseModel):
    player_id: str = Field(..., example="P006")
    match_id: str = Field(..., example="M004")
    region: str = Field(..., example="India")
    device: str = Field(..., example="PC")
    ping: int = Field(..., ge=0, example=45)
    score: int = Field(..., ge=0, example=3100)
    kills: int = Field(..., ge=0, example=15)
    deaths: int = Field(..., ge=0, example=3)
    match_duration_seconds: int = Field(..., ge=1, example=400)


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "Game Ops API"}


@app.post("/submit-score", tags=["Match Data"], status_code=201)
def submit_score(data: MatchSubmission):
    """
    Submit a new match record.
    Appends the row to the CSV file so it persists across requests.
    """
    file_exists = os.path.isfile(DATA_PATH)

    with open(DATA_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "player_id", "match_id", "region", "device",
                "ping", "score", "kills", "deaths", "match_duration_seconds",
            ],
        )
        # Write header only if file was just created (shouldn't happen, but safe)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data.model_dump())

    return {
        "message": "Score submitted successfully.",
        "record": data.model_dump(),
    }


@app.get("/players", tags=["Match Data"])
def list_players(region: Optional[str] = Query(None, description="Filter by region")):
    """
    Return all match records.
    Optionally filter by region (e.g. ?region=India).
    """
    matches = _get_matches()
    result = [vars(m) for m in matches]
    if region:
        result = [r for r in result if r["region"].lower() == region.lower()]
    return {"total": len(result), "records": result}


@app.get("/leaderboard", tags=["Leaderboard"])
def global_leaderboard():
    """
    Global leaderboard ranked by total score.

    Tie-breaking order:
      1. Higher total score → better rank
      2. Fewer total deaths → better rank
      3. More total kills  → better rank

    Flagged/suspicious players are excluded from ranking.
    """
    matches = _get_matches()
    return get_global_leaderboard(matches)


@app.get("/leaderboard/region", tags=["Leaderboard"])
def region_leaderboard():
    """Per-region leaderboards. Flagged players are excluded."""
    matches = _get_matches()
    return get_region_leaderboard(matches)


@app.get("/flagged-players", tags=["Anti-Cheat"])
def flagged_players():
    """
    Two-layer sequential suspicious player detection.

    LAYER 1 — Rule Engine (runs first, deterministic):
      • R1: Score rate > 50 pts/sec
      • R2: Kills > 30 with 0 deaths (godmode)
      • R3: Score > 10,000 in under 120 seconds (impossible combo)
      • R4: Kill rate > 0.2 kills/sec
      • R5: KDR (kills/deaths) > 20
      • R6: Score per kill > 300 pts/kill

    LAYER 2 — Z-Score Statistical Layer (runs on clean baseline):
      Derives 4 features per record: score_rate, kill_rate, kdr, score_per_kill.
      Z-scores each against the population of NON-rule-flagged players only
      (cheaters cannot skew the baseline).
      Flags a record if 2+ features independently exceed z=2.5.
      Also checks raw score against a robust IQR outlier fence.

    Risk levels:
      HIGH   — 3+ evidence items (auto-excluded from leaderboard/matchmaking)
      MEDIUM — 1-2 evidence items with at least one rule hit (also excluded)
      LOW    — z-score layer only, no rule hit (watch-list, not excluded yet)
    """
    matches = _get_matches()
    flagged = detect_suspicious(matches)
    return {
        "total_flagged": len(flagged),
        "high_risk":  sum(1 for f in flagged if f["risk_level"] == "HIGH"),
        "medium_risk": sum(1 for f in flagged if f["risk_level"] == "MEDIUM"),
        "low_risk":   sum(1 for f in flagged if f["risk_level"] == "LOW"),
        "flagged_players": flagged,
    }


@app.get("/matchmaking", tags=["Matchmaking"])
def matchmaking():
    """
    Suggest fair match groups.

    Grouping strategy:
      1. Flagged players are excluded.
      2. Players are bucketed by region (prefer same-region matches).
      3. Within a region, split by ping tier: low (≤80ms), mid (81–150ms), high (>150ms).
      4. Within each bucket, players are sorted by average score (skill proxy)
         and packed into groups of 4.
    """
    matches = _get_matches()
    return suggest_matchmaking(matches)
