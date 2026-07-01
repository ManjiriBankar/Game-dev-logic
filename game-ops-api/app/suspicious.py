"""
suspicious.py
Two-layer sequential suspicious player detection.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 1 — Rule-Based Engine  (fast, deterministic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Six hard rules catch obvious cheaters immediately.
Each rule is independent; triggering ANY rule adds evidence.

  R1 – Score rate > 50 pts/sec
  R2 – Godmode: kills > 30 AND deaths == 0
  R3 – Impossible combo: score > 10 000 in under 120 s
  R4 – Kill rate > 0.2 kills/sec (1 kill per 5 sec)
  R5 – KDR > 20  (kills / deaths ratio)
  R6 – Score per kill > 300 pts/kill

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 2 — Z-Score Statistical Layer  (catches subtle cheaters)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Four derived features are computed for every match and
z-scored against the population of ALL records.

  F1 – score_rate        = score / duration
  F2 – kill_rate         = kills / duration
  F3 – kdr               = kills / max(deaths, 1)
  F4 – score_per_kill    = score / max(kills, 1)

For each feature, z = (value - mean) / std.
If ZSCORE_FEATURES_REQUIRED (default 2) or more features
independently exceed Z_ALERT (default 2.5 σ), the record
is flagged by the statistical layer.

Uses robust statistics (median + IQR) for the outlier fence
on raw scores so that extreme cheaters cannot poison the mean.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RISK CLASSIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CLEAR   – 0 evidence items
  LOW     – only statistical layer hit (1 item), no rule hits
  MEDIUM  – 1–2 evidence items (any mix of rules + z-score)
  HIGH    – 3 or more evidence items → almost certainly cheating

A player is excluded from leaderboard/matchmaking when
risk_level is MEDIUM or HIGH.
"""

import math
import statistics
from typing import List, Dict, Set, Any, Optional

from app.data_loader import PlayerMatch
from app.config import (
    SCORE_RATE_THRESHOLD,
    GODMODE_KILLS_MIN,
    GODMODE_DEATHS_MAX,
    IMPOSSIBLE_SCORE_MIN,
    IMPOSSIBLE_DURATION_MAX,
    KILL_RATE_THRESHOLD,
    KDR_THRESHOLD,
    SCORE_PER_KILL_MAX,
    ZSCORE_MIN_SAMPLES,
    ZSCORE_FEATURES_REQUIRED,
    Z_ALERT,
    IQR_MULTIPLIER,
    IQR_MIN_SAMPLES,
    HIGH_RISK_THRESHOLD,
)


# ═════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Rule-Based Engine
# ═════════════════════════════════════════════════════════════════════════════

def _r1_score_rate(m: PlayerMatch) -> Optional[str]:
    """R1: Score earned per second is superhuman."""
    duration = max(m.match_duration_seconds, 1)
    rate = m.score / duration
    if rate > SCORE_RATE_THRESHOLD:
        return (
            f"[R1] Score rate {rate:.1f} pts/sec "
            f"exceeds threshold of {SCORE_RATE_THRESHOLD}"
        )
    return None


def _r2_godmode(m: PlayerMatch) -> Optional[str]:
    """R2: Many kills with zero deaths — aimbot / invincibility cheat."""
    if m.kills > GODMODE_KILLS_MIN and m.deaths == GODMODE_DEATHS_MAX:
        return (
            f"[R2] {m.kills} kills with 0 deaths "
            f"(godmode pattern, threshold: kills > {GODMODE_KILLS_MIN})"
        )
    return None


def _r3_impossible_combo(m: PlayerMatch) -> Optional[str]:
    """R3: Very high score achieved in a very short match."""
    if m.score > IMPOSSIBLE_SCORE_MIN and m.match_duration_seconds < IMPOSSIBLE_DURATION_MAX:
        return (
            f"[R3] Score {m.score} in only {m.match_duration_seconds}s "
            f"(threshold: score>{IMPOSSIBLE_SCORE_MIN} AND duration<{IMPOSSIBLE_DURATION_MAX}s)"
        )
    return None


def _r4_kill_rate(m: PlayerMatch) -> Optional[str]:
    """R4: Kills per second is superhuman across the entire match."""
    duration = max(m.match_duration_seconds, 1)
    kill_rate = m.kills / duration
    if kill_rate > KILL_RATE_THRESHOLD:
        return (
            f"[R4] Kill rate {kill_rate:.3f} kills/sec "
            f"exceeds threshold of {KILL_RATE_THRESHOLD}"
        )
    return None


def _r5_kdr(m: PlayerMatch) -> Optional[str]:
    """R5: Kill-to-death ratio is impossibly high (not caught by godmode rule)."""
    if m.deaths == 0:
        return None  # handled by R2; avoid double-counting
    kdr = m.kills / m.deaths
    if kdr > KDR_THRESHOLD:
        return (
            f"[R5] KDR {kdr:.1f} (kills={m.kills}, deaths={m.deaths}) "
            f"exceeds threshold of {KDR_THRESHOLD}"
        )
    return None


def _r6_score_per_kill(m: PlayerMatch) -> Optional[str]:
    """R6: Points earned per kill far exceeds what the game normally awards."""
    if m.kills == 0:
        return None  # division guard; score without kills is a separate issue
    spk = m.score / m.kills
    if spk > SCORE_PER_KILL_MAX:
        return (
            f"[R6] Score per kill {spk:.0f} pts/kill "
            f"exceeds threshold of {SCORE_PER_KILL_MAX}"
        )
    return None


# Ordered list — rules run in this sequence, cheapest checks first
_RULE_CHECKS = [_r1_score_rate, _r2_godmode, _r3_impossible_combo,
                _r4_kill_rate, _r5_kdr, _r6_score_per_kill]


def _run_rules(m: PlayerMatch) -> List[str]:
    """Run all rule checks on a single match record. Returns triggered reasons."""
    return [msg for fn in _RULE_CHECKS if (msg := fn(m))]


# ═════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Z-Score Statistical Layer
# ═════════════════════════════════════════════════════════════════════════════

class _FeatureStats:
    """
    Pre-computed per-feature mean and std for a batch of match records.
    Uses only CLEAN records (not rule-flagged) so cheaters cannot
    inflate the population statistics and hide behind the noise they create.
    """

    def __init__(self, records: List[PlayerMatch]):
        # Derived feature vectors
        self.score_rates   = self._rates(records, lambda m: m.score)
        self.kill_rates    = self._rates(records, lambda m: m.kills)
        self.kdrs          = [m.kills / max(m.deaths, 1) for m in records]
        self.spks          = [m.score / max(m.kills, 1) for m in records]

        # Per-feature (mean, std)
        self.score_rate_stats  = self._stats(self.score_rates)
        self.kill_rate_stats   = self._stats(self.kill_rates)
        self.kdr_stats         = self._stats(self.kdrs)
        self.spk_stats         = self._stats(self.spks)

        # Robust IQR fence on raw scores (outlier safety net)
        raw_scores = sorted(m.score for m in records)
        self.iqr_fence = self._iqr_fence(raw_scores)

    @staticmethod
    def _rates(records, value_fn) -> List[float]:
        return [value_fn(m) / max(m.match_duration_seconds, 1) for m in records]

    @staticmethod
    def _stats(values: List[float]):
        """Return (mean, std). Returns (0, 0) if insufficient data."""
        if len(values) < ZSCORE_MIN_SAMPLES:
            return (0.0, 0.0)
        mean = statistics.mean(values)
        std  = statistics.stdev(values) if len(values) > 1 else 0.0
        return (mean, std)

    @staticmethod
    def _iqr_fence(sorted_vals: List[float]) -> Optional[float]:
        """
        Tukey upper fence = Q3 + IQR_MULTIPLIER * IQR.
        Returns None if not enough data.
        """
        n = len(sorted_vals)
        if n < IQR_MIN_SAMPLES:
            return None
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[(3 * n) // 4]
        iqr = q3 - q1
        return q3 + IQR_MULTIPLIER * iqr


def _z(value: float, mean: float, std: float) -> float:
    """Safe z-score — returns 0 if std is zero (all values are identical)."""
    return (value - mean) / std if std > 0 else 0.0


def _run_zscore(m: PlayerMatch, stats: _FeatureStats) -> List[str]:
    """
    Compute z-scores for the four derived features of a single match.
    Returns a list of flagged feature descriptions.

    A feature is flagged when its z-score exceeds Z_ALERT.
    The record is flagged by this layer only when at least
    ZSCORE_FEATURES_REQUIRED features are independently anomalous.
    This prevents a single fluky stat from causing a false positive.
    """
    duration = max(m.match_duration_seconds, 1)

    # Compute per-feature z-scores
    features = [
        (
            "score_rate",
            _z(m.score / duration,          *stats.score_rate_stats),
            f"{m.score / duration:.2f} pts/sec",
        ),
        (
            "kill_rate",
            _z(m.kills / duration,           *stats.kill_rate_stats),
            f"{m.kills / duration:.3f} kills/sec",
        ),
        (
            "kdr",
            _z(m.kills / max(m.deaths, 1),   *stats.kdr_stats),
            f"{m.kills / max(m.deaths, 1):.1f}",
        ),
        (
            "score_per_kill",
            _z(m.score / max(m.kills, 1),    *stats.spk_stats),
            f"{m.score / max(m.kills, 1):.0f} pts/kill",
        ),
    ]

    # Collect features that exceed the alert threshold
    anomalous = [
        f"[Z] {name} z={z:.2f} (value={val}, threshold=±{Z_ALERT})"
        for name, z, val in features
        if z > Z_ALERT                         # one-tailed: only flag high outliers
    ]

    # Also check raw score against robust IQR fence
    if stats.iqr_fence is not None and m.score > stats.iqr_fence:
        anomalous.append(
            f"[Z] Raw score {m.score} exceeds IQR outlier fence "
            f"({stats.iqr_fence:.0f})"
        )

    # Only report if enough features are simultaneously anomalous
    if len(anomalous) >= ZSCORE_FEATURES_REQUIRED:
        return anomalous
    return []


# ═════════════════════════════════════════════════════════════════════════════
# RISK CLASSIFICATION
# ═════════════════════════════════════════════════════════════════════════════

def _classify_risk(rule_hits: List[str], zscore_hits: List[str]) -> str:
    """
    Combine evidence from both layers into a single risk level.

    CLEAR  – nothing triggered
    LOW    – statistical layer only, no rule hits (watch list)
    MEDIUM – 1–2 total evidence items
    HIGH   – 3+ total evidence items
    """
    total = len(rule_hits) + len(zscore_hits)
    if total == 0:
        return "CLEAR"
    if total >= HIGH_RISK_THRESHOLD:
        return "HIGH"
    if rule_hits:
        return "MEDIUM"
    return "LOW"          # z-score only, no hard rule hit


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def detect_suspicious(matches: List[PlayerMatch]) -> List[Dict[str, Any]]:
    """
    Sequential two-layer detection pipeline.

    Step 1 – Run rule engine on every record.
    Step 2 – Build population stats using ONLY records that passed all rules
             (clean baseline — cheaters cannot skew it).
    Step 3 – Run z-score layer on every record against the clean baseline.
    Step 4 – Combine evidence, classify risk, return flagged records.

    Returns a list of dicts for records where risk_level != CLEAR.
    """
    if not matches:
        return []

    # ── Step 1: Rule engine ───────────────────────────────────────────────────
    rule_results: Dict[str, List[str]] = {}      # match index → rule hits
    rule_flagged_ids: Set[str] = set()

    for m in matches:
        hits = _run_rules(m)
        rule_results[id(m)] = hits
        if hits:
            rule_flagged_ids.add(m.player_id)

    # ── Step 2: Build CLEAN baseline (exclude rule-flagged players) ───────────
    clean_records = [m for m in matches if m.player_id not in rule_flagged_ids]

    # Need at least ZSCORE_MIN_SAMPLES clean records for stats to be meaningful
    if len(clean_records) >= ZSCORE_MIN_SAMPLES:
        pop_stats = _FeatureStats(clean_records)
    else:
        pop_stats = None     # not enough clean data — skip z-score layer

    # ── Step 3 + 4: Z-score layer + combine + classify ───────────────────────
    flagged: List[Dict[str, Any]] = []

    for m in matches:
        rule_hits   = rule_results[id(m)]
        zscore_hits = _run_zscore(m, pop_stats) if pop_stats is not None else []
        risk        = _classify_risk(rule_hits, zscore_hits)

        if risk == "CLEAR":
            continue

        flagged.append(
            {
                "player_id":               m.player_id,
                "match_id":                m.match_id,
                "region":                  m.region,
                "device":                  m.device,
                "ping":                    m.ping,
                "score":                   m.score,
                "kills":                   m.kills,
                "deaths":                  m.deaths,
                "match_duration_seconds":  m.match_duration_seconds,
                # Derived metrics shown for transparency
                "derived": {
                    "score_rate":      round(m.score / max(m.match_duration_seconds, 1), 2),
                    "kill_rate":       round(m.kills / max(m.match_duration_seconds, 1), 4),
                    "kdr":             round(m.kills / max(m.deaths, 1), 2),
                    "score_per_kill":  round(m.score / max(m.kills, 1), 2),
                },
                "rule_hits":    rule_hits,
                "zscore_hits":  zscore_hits,
                "total_evidence": len(rule_hits) + len(zscore_hits),
                "risk_level":   risk,
                # Which layer(s) caught this player
                "detected_by":  _detection_source(rule_hits, zscore_hits),
            }
        )

    # Sort output: HIGH first, then MEDIUM, then LOW
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    flagged.sort(key=lambda x: order.get(x["risk_level"], 9))
    return flagged


def get_flagged_player_ids(matches: List[PlayerMatch]) -> Set[str]:
    """
    Return the set of player IDs whose risk_level is MEDIUM or HIGH.
    LOW (z-score watch-list only) players are NOT excluded from leaderboard —
    they are monitored but not penalised yet.
    """
    return {
        entry["player_id"]
        for entry in detect_suspicious(matches)
        if entry["risk_level"] in ("MEDIUM", "HIGH")
    }


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detection_source(rule_hits: List[str], zscore_hits: List[str]) -> str:
    if rule_hits and zscore_hits:
        return "RULES + ZSCORE"
    if rule_hits:
        return "RULES"
    return "ZSCORE"
