# Game Ops System API

A FastAPI backend for processing multiplayer game match data during a live event.

## Features
- Submit and store match scores
- Global & region-wise leaderboard (with tie-breaking rules)
- Suspicious / cheat player detection (rule-based)
- Skill + region + ping-aware matchmaking groups

## Project Structure
```
game-ops-api/
├── app/
│   ├── main.py          # FastAPI app & all routes
│   ├── data_loader.py   # CSV loader & PlayerMatch dataclass
│   ├── leaderboard.py   # Global + region leaderboard logic
│   ├── suspicious.py    # Rule-based cheat detection
│   └── matchmaking.py   # Matchmaking group builder
├── data/
│   └── matches.csv      # Seed data (appended on POST /submit-score)
├── requirements.txt
└── README.md
```

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
uvicorn app.main:app --reload
```

Server runs at: http://127.0.0.1:8000  
Interactive docs: http://127.0.0.1:8000/docs

## API Endpoints

| Method | Endpoint              | Description                          |
|--------|-----------------------|--------------------------------------|
| GET    | /health               | Liveness check                       |
| GET    | /players              | All match records (filter by region) |
| POST   | /submit-score         | Submit a new match result            |
| GET    | /leaderboard          | Global ranked leaderboard            |
| GET    | /leaderboard/region   | Per-region leaderboards              |
| GET    | /flagged-players      | Suspicious player detection results  |
| GET    | /matchmaking          | Suggested fair match groups          |

## Suspicious Detection Rules
1. Score rate > 50 pts/sec
2. More than 30 kills with 0 deaths
3. Score > 10,000 AND match duration < 120 seconds
4. Kill rate > 1 kill per 5 seconds
5. Score is a statistical outlier (mean + 3 × std dev)

## Matchmaking Logic
- Players grouped by region first
- Within region, split into ping tiers: Low (≤80ms), Mid (81–150ms), High (>150ms)
- Sorted by average score (skill proxy), packed into groups of 4
- Flagged players excluded entirely
