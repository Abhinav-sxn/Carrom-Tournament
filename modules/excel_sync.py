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
import threading
import time
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

LOCATIONS = ["Bangalore", "Hyderabad", "Indore"]

# Per-thread location: each Streamlit session runs in its own thread so
# using threading.local() means concurrent sessions never clobber each other.
_tls = threading.local()


def _get_location() -> str:
    """Return the active location for the current thread, defaulting to LOCATIONS[0]."""
    return getattr(_tls, "active_location", LOCATIONS[0])


def set_location(loc: str) -> None:
    """Switch active location for this thread only — other sessions are unaffected."""
    _tls.active_location = loc


def _csv_path(sheet_name: str, location: str | None = None) -> str:
    loc = (location or _get_location()).lower()
    return os.path.join(DATA_DIR, loc, f"{sheet_name.lower()}.csv")


def _repo_path(sheet_name: str, location: str | None = None) -> str:
    """GitHub repo-relative path for a sheet's CSV file."""
    loc = (location or _get_location()).lower()
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
    "Players": ["player_id", "name", "skill_rating", "team_id", "partner_pref"],
    "Teams": [
        "team_id", "team_name", "avg_skill",
        "wins", "losses", "is_eliminated",
    ],
    "Matches": [
        "match_id", "round", "team_a_id", "team_b_id",
        "winner_id", "loser_id", "bracket", "status", "scheduled_date", "scheduled_time", "date_played",
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
    loc = (location or _get_location()).lower()
    os.makedirs(os.path.join(DATA_DIR, loc), exist_ok=True)


# ---------------------------------------------------------------------------
# Deferred GitHub push — dirty tracking + background thread
# ---------------------------------------------------------------------------

_dirty_sheets: set[tuple[str, str]] = set()  # (sheet_name, location)
_dirty_lock   = threading.Lock()
_bg_thread: threading.Thread | None = None
_PUSH_INTERVAL = 300  # seconds between automatic background pushes


def _mark_dirty(sheet_name: str) -> None:
    """Flag a sheet+location pair as needing a GitHub push.
    Location is captured from the current thread now, not at push time.
    """
    with _dirty_lock:
        _dirty_sheets.add((sheet_name, _get_location()))


def _bg_push_loop() -> None:
    """Background daemon: push dirty sheets every _PUSH_INTERVAL seconds."""
    while True:
        time.sleep(_PUSH_INTERVAL)
        sync_to_github()


def _ensure_bg_thread() -> None:
    global _bg_thread
    if _bg_thread is None or not _bg_thread.is_alive():
        t = threading.Thread(target=_bg_push_loop, daemon=True, name="github-sync")
        t.start()
        _bg_thread = t


def sync_to_github() -> dict:
    """Push all dirty sheets to GitHub immediately.

    Safe to call from any thread — does not use st.session_state or st.warning.
    Returns {"pushed": [..."location/sheet"...], "failed": [...]}.
    """
    with _dirty_lock:
        items = list(_dirty_sheets)
        _dirty_sheets.clear()

    pushed: list[str] = []
    failed: list[str] = []
    for sheet_name, location in items:
        path = _csv_path(sheet_name, location)       # use stored location
        repo  = _repo_path(sheet_name, location)     # use stored location
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
            from modules.github_sync import push_file
            push_file(repo, df.to_csv(index=False), f"Sync {location}/{sheet_name}")
            pushed.append(f"{location}/{sheet_name}")
        except Exception:
            failed.append(f"{location}/{sheet_name}")
            with _dirty_lock:                       # re-queue with correct location
                _dirty_sheets.add((sheet_name, location))

    return {"pushed": pushed, "failed": failed}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_data_store() -> None:
    """On startup pull any missing CSVs from GitHub in parallel, then create empty
    placeholders for any still absent.  Parallel fetches cut cold-start latency
    from ~N×0.5 s (sequential) down to ~0.5 s total.
    """
    _ensure_data_dir()
    missing = [
        sn for sn in SHEET_HEADERS if not os.path.exists(_csv_path(sn))
    ]

    if missing:
        import concurrent.futures

        def _pull_one(sheet_name: str) -> None:
            try:
                from modules.github_sync import pull_file
                content = pull_file(_repo_path(sheet_name))
                if content:
                    pd.read_csv(io.StringIO(content)).to_csv(
                        _csv_path(sheet_name), index=False
                    )
                    return
            except Exception:
                pass
            if not os.path.exists(_csv_path(sheet_name)):
                pd.DataFrame(columns=SHEET_HEADERS[sheet_name]).to_csv(
                    _csv_path(sheet_name), index=False
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(missing), 6)
        ) as pool:
            list(pool.map(_pull_one, missing))
    else:
        # All files present locally — nothing to do
        pass


# Keep backward-compatible alias used by Main.py
init_workbook = init_data_store


# ---------------------------------------------------------------------------
# Cached CSV reader — shared across all Streamlit sessions in this process.
# Cache is busted in save_sheet() via st.cache_data.clear().
# Falls back to uncached when running outside Streamlit (unit tests, CLI).
# ---------------------------------------------------------------------------

def _load_csv_from_path(path: str, sheet_name: str) -> pd.DataFrame:
    """Read a CSV from disk and return a typed DataFrame."""
    expected_cols = SHEET_HEADERS.get(sheet_name, [])
    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame(columns=expected_cols)
        # Backfill any columns added to SHEET_HEADERS after this CSV was saved
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception:
        return pd.DataFrame(columns=expected_cols)


try:
    import streamlit as _st
    _load_csv_from_path = _st.cache_data(show_spinner=False)(_load_csv_from_path)
except Exception:
    pass  # not running inside Streamlit — use uncached version


def load_sheet(sheet_name: str, location: str | None = None) -> pd.DataFrame:
    """Load a sheet from its CSV file.

    If the local file is absent (e.g. after a Streamlit Cloud container restart),
    the latest version is pulled from GitHub before falling back to an empty frame.

    Pass *location* to read a specific location's data without touching the
    module-level active location.  Omit it (or pass None) to use the current
    active location (the normal case for all page modules).
    """
    _ensure_data_dir(location)
    expected_cols = SHEET_HEADERS.get(sheet_name, [])
    path = _csv_path(sheet_name, location)

    if not os.path.exists(path):
        # Recovery path: pull from GitHub and write to disk, then fall through
        try:
            from modules.github_sync import pull_file
            content = pull_file(_repo_path(sheet_name, location))
            if content:
                df = pd.read_csv(io.StringIO(content))
                df.to_csv(path, index=False)
        except Exception:
            pass
        if not os.path.exists(path):
            return pd.DataFrame(columns=expected_cols)

    return _load_csv_from_path(path, sheet_name)


def save_sheet(sheet_name: str, df: pd.DataFrame) -> None:
    """Overwrite a sheet's CSV file and commit it to GitHub.

    Automatically recomputes derived sheets (Leaderboard, PlayerStats)
    when saving source data.
    """
    _ensure_data_dir()
    df.to_csv(_csv_path(sheet_name), index=False)

    # Bust ALL cached reads + workbook so the next rerun sees fresh data,
    # then mark dirty for deferred GitHub push when admin is active.
    try:
        import streamlit as st
        st.cache_data.clear()
        if st.session_state.get("is_admin", False):
            _mark_dirty(sheet_name)
            _ensure_bg_thread()
    except Exception:
        pass

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
    if teams_df.empty:
        pd.DataFrame(columns=SHEET_HEADERS["Leaderboard"]).to_csv(
            _csv_path("Leaderboard"), index=False
        )
        _mark_dirty("Leaderboard")
    else:
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
        _mark_dirty("Leaderboard")

    # ---- PlayerStats -------------------------------------------------------
    if players_df.empty:
        pd.DataFrame(columns=SHEET_HEADERS["PlayerStats"]).to_csv(
            _csv_path("PlayerStats"), index=False
        )
        _mark_dirty("PlayerStats")
    else:
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
        _mark_dirty("PlayerStats")
