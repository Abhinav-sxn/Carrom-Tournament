# Carrom Board Tournament — Project Plan

---

## 1. Project Overview

A desktop/local web app to manage a Carrom Board Tournament end-to-end:
- Register players with skill ratings
- Auto-generate balanced teams
- Schedule matches
- Record match results (win/loss) and per-match player awards
- Track standings with a double-elimination format
- Sync all data to/from an Excel workbook for offline sharing and analytics

---

## 2. Tournament Format

### 2.1 Elimination Rules
- Each match result is a **boolean Win or Loss** per team
- A team that loses gets placed in a **losers bracket**
- A team can lose **up to 2 times** before being **knocked out** (double-elimination style)
- The final match is between the last team from the winners bracket vs. the last surviving team from the losers bracket

### 2.2 Team Composition
- Players are input with a **skill rating** (e.g. 1–10)
- The app **auto-pairs players** so that every team has a similar average skill level (balanced pairing algorithm)
- After pairing, the umpire/organizer can optionally **assign a team name**

---

## 3. Data Models

### 3.1 Player
| Field         | Type    | Description                        |
|---------------|---------|------------------------------------|
| player_id     | int     | Unique identifier                  |
| name          | string  | Player full name                   |
| skill_rating  | float   | Self-reported skill level (1–10)   |
| team_id       | int FK  | Assigned team                      |

### 3.2 Team
| Field         | Type    | Description                        |
|---------------|---------|------------------------------------|
| team_id       | int     | Unique identifier                  |
| team_name     | string  | Custom name (optional, default: "Team A" etc.) |
| avg_skill     | float   | Average skill of team members      |
| wins          | int     | Total wins                         |
| losses        | int     | Total losses (max 2 before KO)     |
| is_eliminated | bool    | True when loss count reaches 3     |

### 3.3 Match
| Field         | Type    | Description                        |
|---------------|---------|------------------------------------|
| match_id      | int     | Unique identifier                  |
| round         | int     | Tournament round number            |
| team_a_id     | int FK  | First team                         |
| team_b_id     | int FK  | Second team                        |
| winner_id     | int FK  | Winning team (nullable until played)|
| loser_id      | int FK  | Losing team                        |
| bracket       | string  | "winners" or "losers"              |
| status        | string  | "scheduled", "in_progress", "done" |
| date_played   | date    | Date of the match                  |

### 3.4 Match Player Stats (per player, per match)
| Field              | Type  | Description                                      |
|--------------------|-------|--------------------------------------------------|
| stat_id            | int   | Unique identifier                                |
| match_id           | int FK| Linked match                                     |
| player_id          | int FK| Linked player                                    |
| team_id            | int FK| Player's team in this match                      |
| silent_assassin    | bool  | Scored quietly without drawing attention         |
| queen_snatcher     | bool  | Pocketed the Queen decisively                    |
| precision_player   | bool  | Consistently accurate shots                      |
| best_striker       | bool  | Most powerful and effective strike play          |
| comeback_king      | bool  | Turned the game around after a deficit           |
| board_controller   | bool  | Dominated board positioning throughout           |
| clutch_player      | bool  | Delivered under high-pressure moments            |

> **Award Rules:** Each award is a **boolean (0 or 1)** assigned by the umpire per match. Multiple players can hold different awards in the same match. Awards are match-scoped — they do not carry over automatically.

---

## 4. Player Awards Glossary

| Award            | Description                                              |
|------------------|----------------------------------------------------------|
| Silent Assassin  | Scores consistently without flashy moves; hard to read  |
| Queen Snatcher   | Successfully pockets the Queen and covers it            |
| Precision Player | Highest shot accuracy throughout the match              |
| Best Striker     | Most impactful/powerful striking performance            |
| Comeback King    | Team was losing; this player reversed the momentum      |
| Board Controller | Dictated piece positioning and flow of the game         |
| Clutch Player    | Scored or defended at the most critical point           |

---

## 5. Scoring & Leaderboard Logic

### 5.1 Team Leaderboard
- Ranked by: `wins DESC`, then `losses ASC`, then `total awards ASC`
- Shows: Team name, wins, losses, status (Active / Eliminated)

### 5.2 Player Leaderboard
- Ranked by total award count across all matches
- Columns: Player name, team, each award count, total awards
- Highlights: Most decorated player per award category

---

## 6. Excel Workbook Schema

The app reads from and writes to a single `.xlsx` file with the following sheets:

| Sheet Name       | Contents                                      |
|------------------|-----------------------------------------------|
| `Players`        | All player records                            |
| `Teams`          | All team records with win/loss totals         |
| `Matches`        | Full match schedule and results               |
| `MatchStats`     | Per-player per-match award data               |
| `Leaderboard`    | Auto-computed team standings (formula-driven) |
| `PlayerStats`    | Aggregated player award totals                |

- The Excel file is the **single source of truth**
- The app reads from Excel on launch and writes back after every change
- The Excel file can be shared independently for offline viewing

---

## 7. App Architecture

### 7.1 Technology Stack (Recommended)
| Layer       | Choice       | Reason                                                  |
|-------------|--------------|---------------------------------------------------------|
| Language    | Python       | Easy Excel I/O, cross-platform, no install              |
| UI          | ✅ Streamlit  | Browser-based, works on Windows + mobile out of the box |
| Excel I/O   | openpyxl     | Read/write `.xlsx` without Excel installed              |
| Packaging   | `streamlit run` on Windows, accessible via local network on mobile |

### 7.2 Module Breakdown
```
carrom_tournament/
├── main.py                  # App entry point
├── data/
│   └── tournament.xlsx      # Excel data file
├── modules/
│   ├── player_manager.py    # Add/edit/list players
│   ├── team_builder.py      # Balanced team pairing algorithm
│   ├── match_scheduler.py   # Generate match schedule
│   ├── match_recorder.py    # Record results + awards
│   ├── leaderboard.py       # Compute standings
│   └── excel_sync.py        # Read/write Excel workbook
├── ui/
│   ├── pages/
│   │   ├── 01_Players.py
│   │   ├── 02_Teams.py
│   │   ├── 03_Schedule.py
│   │   ├── 04_Record_Match.py
│   │   └── 05_Leaderboard.py
│   └── components/          # Reusable UI components
└── requirements.txt
```

---

## 8. Balanced Team Pairing Algorithm

**Goal:** Given N players each with a skill rating, form teams of 2 so that all team averages are as close as possible.

**Approach — Sorted Interleaving:**
1. Sort all players by skill rating descending
2. Pair player[0] with player[N-1], player[1] with player[N-2], etc.
3. This ensures the highest-rated is paired with the lowest, balancing averages
4. If N is odd, one player gets a bye or joins a 3-player team

**Validation:** After pairing, display team averages to the organizer for approval before locking teams.

---

## 9. Match Scheduling Logic

1. **Round 1:** All teams play against each other in random order (single round-robin seed round OR direct bracket draw — TBD by organizer)
2. **Winners Bracket:** Winners advance; losers drop to Losers Bracket
3. **Losers Bracket:** Losers play again; second loss = elimination
4. **Finals:** Last winner from Winners Bracket vs. survivor of Losers Bracket

> Schedule is generated upfront and stored in the `Matches` sheet. The umpire marks each match as played and inputs the result.

---

## 10. Implementation Steps

### Phase 1 — Foundation
- [ ] Set up Python project structure and `requirements.txt`
- [ ] Create and initialize the Excel workbook with all sheets and headers
- [ ] Build `excel_sync.py` — load/save all data to Excel

### Phase 2 — Player & Team Management
- [ ] Build `player_manager.py` — add players with skill ratings
- [ ] Build `team_builder.py` — balanced pairing algorithm + team naming
- [ ] UI: Players page (add, list, assign to teams)
- [ ] UI: Teams page (view pairs, edit team names)

### Phase 3 — Match Scheduling
- [ ] Build `match_scheduler.py` — generate bracket and schedule
- [ ] UI: Schedule page (view all matches, round labels, bracket type)

### Phase 4 — Match Recording
- [ ] Build `match_recorder.py` — record win/loss, assign awards per player
- [ ] UI: Record Match page — dropdown to select match, mark winner, toggle awards
- [ ] Auto-update team win/loss counters and elimination status

### Phase 5 — Leaderboard & Stats
- [ ] Build `leaderboard.py` — compute team standings and player award totals
- [ ] UI: Leaderboard page — team table + player awards table
- [ ] Excel: Auto-update `Leaderboard` and `PlayerStats` sheets on save

### Phase 6 — Polish & Distribution
- [ ] Add input validation and error handling
- [ ] Test full tournament flow end-to-end
- [ ] Package with PyInstaller into a standalone `.exe` (optional)
- [ ] Final Excel layout formatting (colors, bold headers, freeze panes)

---

## 11. Open Questions (Decide Before Build)

| # | Question                                                             | Default Assumption          |
|---|----------------------------------------------------------------------|-----------------------------|
| 1 | How many players per team? (2v2 standard carrom?)                   | ✅ 2 players per team        |
| 2 | Is the initial round a full round-robin or single-elimination draw? | ✅ Random bracket draw       |
| 3 | Can the same award be given to multiple players in one match?       | Yes                         |
| 4 | Should the Excel sheet be protected/locked except for data entry?   | No protection initially     |
| 5 | Target OS for distribution? (Windows only or cross-platform?)       | ✅ Windows + Mobile (Streamlit web) |
| 6 | Does the umpire use the app live during matches or after?           | After each match            |

---

*Plan created: April 30, 2026*
