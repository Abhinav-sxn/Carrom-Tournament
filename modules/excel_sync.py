"""
excel_sync.py
-------------
Single source of truth for all data read/write operations.
Data is stored as CSV files (one per sheet per location) under data/<location>/.

All other modules call load_sheet() and save_sheet() — never deal with files directly.

On every save_sheet() call the CSV is also committed to GitHub via github_sync so that
data survives Streamlit Cloud container restarts.  Excel files are never stored on disk;
use excel_export.generate_workbook_bytes() to produce an in-memory xlsx for download.

Sheets:
  Players      — registered players with skill ratings
  Teams        — formed teams with win/loss counters
  Matches      — full match schedule and results
  MatchStats   — per-player per-match award flags
  Leaderboard  — auto-computed team standings (derived)
  PlayerStats  — auto-computed player award totals (derived)
"""

from __future__ import annotations

import io
import os
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

LOCATIONS = ["Bangalore", "Hyderabad", "Indore"]
_active_location: str = LOCATIONS[0]


def set_location(loc: str) -> None:
    """Switch active location — all subsequent data calls use this location's CSV files."""
    global _active_location
    _active_location = loc


def _csv_path(sheet_name: str, location: str | None = None) -> str:
    loc = (location or _active_location).lower()
    return os.path.join(DATA_DIR, loc, f"{sheet_name.lower()}.csv")


def _repo_path(sheet_name: str, location: str | None = None) -> str:
    """GitHub repo-relative path for a sheet's CSV file."""
    loc = (location or _active_location).lower()
    return f"data/{loc}/{sheet_name.lower()}.csv"

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

AWARDS = [
    "queen_snatcher",
    "precision_player",
    "best_striker",
    "comeback_king",
]

SHEET_HEADERS = {
    "Players": ["player_id", "name", "skill_rating", "team_id"],
    "Teams": [
        "team_id", "team_name", "avg_skill",
        "wins", "losses", "is_eliminated",
    ],
    "Matches": [
        "match_id", "round", "team_a_id", "team_b_id",
        "winner_id", "loser_id", "bracket", "status", "date_played",
        "team_a_score", "team_b_score",
    ],
    "MatchStats": ["stat_id", "match_id", "player_id", "team_id"] + AWARDS,
    "Leaderboard": [
        "rank", "team_id", "team_name",
        "wins", "losses", "status", "total_points", "total_awards",
    ],
    "PlayerStats": ["player_id", "name", "team_name"] + AWARDS + ["total_awards"],
}

HEADER_COLORS = {
    "Players":     "4472C4",   # Blue
    "Teams":       "70AD47",   # Green
    "Matches":     "ED7D31",   # Orange
    "MatchStats":  "7030A0",   # Purple
    "Leaderboard": "C00000",   # Red
    "PlayerStats": "00B0F0",   # Light blue
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_data_dir(location: str | None = None) -> None:
    loc = (location or _active_location).lower()
    os.makedirs(os.path.join(DATA_DIR, loc), exist_ok=True)


def _push(sheet_name: str, df: pd.DataFrame, message: str | None = None) -> None:
    """Best-effort GitHub commit — never raises."""
    try:
        from modules.github_sync import push_file
        push_file(
            _repo_path(sheet_name),
            df.to_csv(index=False),
            message or f"Update {sheet_name} data",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_data_store() -> None:
    """Create empty CSV files for all sheets if they don't exist locally."""
    _ensure_data_dir()
    for sheet_name, headers in SHEET_HEADERS.items():
        path = _csv_path(sheet_name)
        if not os.path.exists(path):
            pd.DataFrame(columns=headers).to_csv(path, index=False)


# Keep backward-compatible alias used by Main.py
init_workbook = init_data_store


def load_sheet(sheet_name: str) -> pd.DataFrame:
    """Load a sheet from its CSV file.

    If the local file is absent (e.g. after a Streamlit Cloud container restart),
    the latest version is pulled from GitHub before falling back to an empty frame.
    """
    _ensure_data_dir()
    expected_cols = SHEET_HEADERS.get(sheet_name, [])
    path = _csv_path(sheet_name)

    if not os.path.exists(path):
        # Try to restore from GitHub
        try:
            from modules.github_sync import pull_file
            content = pull_file(_repo_path(sheet_name))
            if content:
                df = pd.read_csv(io.StringIO(content))
                df.to_csv(path, index=False)
                return df if not df.empty else pd.DataFrame(columns=expected_cols)
        except Exception:
            pass
        return pd.DataFrame(columns=expected_cols)

    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame(columns=expected_cols)
        return df
    except Exception:
        return pd.DataFrame(columns=expected_cols)


def save_sheet(sheet_name: str, df: pd.DataFrame) -> None:
    """Overwrite a sheet's CSV file and commit it to GitHub.

    Automatically recomputes derived sheets (Leaderboard, PlayerStats)
    when saving source data.
    """
    _ensure_data_dir()
    df.to_csv(_csv_path(sheet_name), index=False)
    _push(sheet_name, df)

    if sheet_name in ("Players", "Teams", "Matches", "MatchStats"):
        update_derived_sheets()


def get_next_id(sheet_name: str, id_column: str) -> int:
    """Return the next available integer ID for a sheet's ID column."""
    df = load_sheet(sheet_name)
    if df.empty or id_column not in df.columns or df[id_column].dropna().empty:
        return 1
    return int(df[id_column].dropna().max()) + 1


def update_derived_sheets() -> None:
    """Recompute Leaderboard and PlayerStats from source data and save as CSVs.

    Called automatically by save_sheet() whenever source data changes.
    """
    _ensure_data_dir()

    teams_df   = load_sheet("Teams")
    players_df = load_sheet("Players")
    ms_df      = load_sheet("MatchStats")
    matches_df = load_sheet("Matches")

    # ---- Leaderboard -------------------------------------------------------
    if not teams_df.empty:
        lb = teams_df[["team_id", "team_name", "wins", "losses", "is_eliminated"]].copy()
        lb["wins"]   = pd.to_numeric(lb["wins"],   errors="coerce").fillna(0).astype(int)
        lb["losses"] = pd.to_numeric(lb["losses"], errors="coerce").fillna(0).astype(int)

        # Total points per team (sum of score in every completed match)
        if not matches_df.empty:
            done_m = matches_df[matches_df["status"] == "done"].copy()
            if not done_m.empty:
                done_m["team_a_score"] = pd.to_numeric(done_m["team_a_score"], errors="coerce").fillna(0)
                done_m["team_b_score"] = pd.to_numeric(done_m["team_b_score"], errors="coerce").fillna(0)
                score_a = done_m[["team_a_id", "team_a_score"]].rename(
                    columns={"team_a_id": "team_id", "team_a_score": "score"}
                )
                score_b = done_m[["team_b_id", "team_b_score"]].rename(
                    columns={"team_b_id": "team_id", "team_b_score": "score"}
                )
                all_scores = pd.concat([score_a, score_b], ignore_index=True).dropna(subset=["team_id"])
                all_scores["team_id"] = pd.to_numeric(all_scores["team_id"], errors="coerce")
                team_pts = all_scores.groupby("team_id")["score"].sum().reset_index(name="total_points")
                lb = lb.merge(team_pts, on="team_id", how="left")
            else:
                lb["total_points"] = 0
        else:
            lb["total_points"] = 0
        lb["total_points"] = lb["total_points"].fillna(0).astype(int)

        # Total awards per team
        if not ms_df.empty and not players_df.empty:
            pid_to_tid = players_df.dropna(subset=["player_id"]).set_index("player_id")["team_id"].to_dict()
            ms = ms_df.copy()
            ms["team_id"] = ms["player_id"].map(pid_to_tid)
            award_sum = (
                ms.groupby("team_id")[AWARDS]
                .sum()
                .sum(axis=1)
                .reset_index(name="total_awards")
            )
            lb = lb.merge(award_sum, on="team_id", how="left")
        else:
            lb["total_awards"] = 0

        lb["total_awards"] = lb["total_awards"].fillna(0).astype(int)
        lb["status"] = lb["is_eliminated"].apply(
            lambda x: "Eliminated" if (x is True or x == 1) else "Active"
        )
        lb = lb.sort_values(
            ["total_points", "wins", "losses"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        lb.insert(0, "rank", range(1, len(lb) + 1))
        lb = lb[["rank", "team_id", "team_name", "wins", "losses", "status", "total_points", "total_awards"]]

        lb.to_csv(_csv_path("Leaderboard"), index=False)
        _push("Leaderboard", lb, "Update Leaderboard")

    # ---- PlayerStats -------------------------------------------------------
    if not players_df.empty:
        ps = players_df[["player_id", "name", "team_id"]].copy()

        if not teams_df.empty:
            tname_map = teams_df.set_index("team_id")["team_name"].to_dict()
            ps["team_name"] = ps["team_id"].map(tname_map).fillna("Unassigned")
        else:
            ps["team_name"] = "Unassigned"

        if not ms_df.empty:
            award_totals = (
                ms_df.dropna(subset=["player_id"])
                .groupby("player_id")[AWARDS]
                .sum()
                .reset_index()
            )
            ps = ps.merge(award_totals, on="player_id", how="left")

        for a in AWARDS:
            if a not in ps.columns:
                ps[a] = 0
            ps[a] = pd.to_numeric(ps[a], errors="coerce").fillna(0).astype(int)

        ps["total_awards"] = ps[AWARDS].sum(axis=1)
        ps = ps[["player_id", "name", "team_name"] + AWARDS + ["total_awards"]]

        ps.to_csv(_csv_path("PlayerStats"), index=False)
        _push("PlayerStats", ps, "Update PlayerStats")
