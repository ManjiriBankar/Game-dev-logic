"""
config.py
Central configuration for all detection thresholds.

Keeping thresholds here means a game patch or new mode never
requires touching business logic — only this file changes.
"""

# ── Rule-based thresholds ─────────────────────────────────────────────────────

# R1 – Score per second
SCORE_RATE_THRESHOLD: float = 50.0          # pts/sec

# R2 – Godmode (high kills, zero deaths)
GODMODE_KILLS_MIN: int = 30                 # kills
GODMODE_DEATHS_MAX: int = 0                 # must be exactly 0

# R3 – Impossible score/duration combo
IMPOSSIBLE_SCORE_MIN: int = 10_000          # points
IMPOSSIBLE_DURATION_MAX: int = 120          # seconds

# R4 – Kill rate
KILL_RATE_THRESHOLD: float = 0.2            # kills/sec (= 1 kill per 5 sec)

# R5 – KDR spike (new)
# Set high enough that a legitimately elite player (28 kills, 1 death = 28 KDR)
# is not caught here — the z-score layer will still catch statistical anomalies.
KDR_THRESHOLD: float = 40.0                 # kills / deaths ratio

# R6 – Score per kill (new)
SCORE_PER_KILL_MAX: float = 300.0           # points per kill

# ── Z-score thresholds ────────────────────────────────────────────────────────

# Minimum number of records needed before z-score is meaningful
ZSCORE_MIN_SAMPLES: int = 3

# Number of derived features that must independently exceed Z_ALERT
# before a z-score flag is raised
ZSCORE_FEATURES_REQUIRED: int = 2

# Z-score value above which a single feature is considered anomalous
Z_ALERT: float = 2.5                        # ~1% tail on each feature

# ── Robust outlier (IQR-based, replaces mean+3σ) ─────────────────────────────

# Tukey upper fence multiplier  → Q3 + IQR_MULTIPLIER * IQR
IQR_MULTIPLIER: float = 3.0
IQR_MIN_SAMPLES: int = 5                    # need at least 5 points for IQR

# ── Risk classification ───────────────────────────────────────────────────────

# Number of total evidence items (rule hits + z-score hits) for HIGH risk
HIGH_RISK_THRESHOLD: int = 3
