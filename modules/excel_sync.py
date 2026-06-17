"""
excel_sync.py
-------------
Single source of truth for all data read/write operations.
Data is stored in Supabase (if configured) with secondary local CSV backup.

All other modules call load_sheet() and save_sheet() — never deal with files directly.

Excel files are never stored on disk; use excel_export.generate_workbook_bytes()
to produce an in-memory xlsx for download.

Sheets:
  Players      — registered players with skill ratings
  Teams        — formed teams with win/loss counters
  Matches      — full match schedule and results
  MatchStats   — per-player per-match award flags
  Leaderboard  — auto-computed team standings (derived)
  PlayerStats  — auto-computed player award totals (derived)
"""

from __future__ import annotations

import os
import threading
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
# Public API
# ---------------------------------------------------------------------------

def init_data_store() -> None:
    """On startup, ensure location-specific data directories and CSV files exist."""
    _ensure_data_dir()
    for sheet_name, headers in SHEET_HEADERS.items():
        path = _csv_path(sheet_name)
        if not os.path.exists(path):
            pd.DataFrame(columns=headers).to_csv(path, index=False)


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





def _sheet_to_supabase_table(sheet_name: str) -> str:
    mapping = {
        "Players": "players",
        "Teams": "teams",
        "Matches": "matches",
        "MatchStats": "match_stats",
        "Leaderboard": "leaderboard",
        "PlayerStats": "player_stats",
    }
    return mapping.get(sheet_name, sheet_name.lower())


def _get_supabase_client():
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if url and key:
            url = url.strip()
            if url.endswith("/rest/v1/"):
                url = url[:-9]
            elif url.endswith("/rest/v1"):
                url = url[:-8]
            from supabase import create_client
            return create_client(url, key)
    except Exception:
        pass
    return None


def _check_supabase_connection(url: str, key: str) -> dict:
    try:
        if url:
            url = url.strip()
            if url.endswith("/rest/v1/"):
                url = url[:-9]
            elif url.endswith("/rest/v1"):
                url = url[:-8]
        from supabase import create_client
        client = create_client(url, key)
        # Select a single row from players table to check read access
        client.table("players").select("player_id").limit(1).execute()
        return {"status": "supabase", "message": "Supabase Cloud"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


try:
    import streamlit as _st
    _check_supabase_connection = _st.cache_data(ttl=10, show_spinner=False)(_check_supabase_connection)
except Exception:
    pass


def get_db_status() -> dict:
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if url and key:
            return _check_supabase_connection(url, key)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "local", "message": "Local CSV"}



def _load_from_supabase(sheet_name: str, location: str) -> pd.DataFrame | None:
    client = _get_supabase_client()
    if client is None:
        return None
    try:
        table_name = _sheet_to_supabase_table(sheet_name)
        response = client.table(table_name).select("*").eq("location", location).execute()
        data = response.data
        expected_cols = SHEET_HEADERS.get(sheet_name, [])
        if not data:
            return pd.DataFrame(columns=expected_cols)
        df = pd.DataFrame(data)
        # Drop the auto-generated serial 'id' column Supabase adds — it is not
        # part of our schema and causes primary-key conflicts when re-inserted.
        if "id" in df.columns:
            df = df.drop(columns=["id"])
        if "location" in df.columns:
            df = df.drop(columns=["location"])
        # Backfill any columns added to SHEET_HEADERS
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None
        df = df[[col for col in expected_cols if col in df.columns]]
        return df
    except Exception as e:
        print(f"Supabase load failed for {sheet_name} ({location}): {e}")
        return None


try:
    import streamlit as _st
    _load_from_supabase = _st.cache_data(ttl=10, show_spinner=False)(_load_from_supabase)
except Exception:
    pass


def load_sheet(sheet_name: str, location: str | None = None) -> pd.DataFrame:
    """Load a sheet from Supabase (if configured) or fallback to its CSV file."""
    loc = (location or _get_location()).lower()
    
    # Try Supabase first
    supabase_df = _load_from_supabase(sheet_name, loc)
    if supabase_df is not None:
        return supabase_df
        
    # Fallback to local CSV
    _ensure_data_dir(location)
    expected_cols = SHEET_HEADERS.get(sheet_name, [])
    path = _csv_path(sheet_name, location)

    if not os.path.exists(path):
        return pd.DataFrame(columns=expected_cols)

    return _load_csv_from_path(path, sheet_name)


def load_sheets(sheet_names: list[str], location: str | None = None) -> dict[str, pd.DataFrame]:
    """Load multiple sheets in parallel using a thread pool to optimize load times.

    Returns a dict mapping sheet_name -> DataFrame.
    """
    import concurrent.futures
    loc = location or _get_location()

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(sheet_names), 6)) as executor:
        futures = {executor.submit(load_sheet, sn, loc): sn for sn in sheet_names}
        for future in concurrent.futures.as_completed(futures):
            sn = futures[future]
            try:
                results[sn] = future.result()
            except Exception as e:
                print(f"Parallel load failed for {sn}: {e}")
                results[sn] = pd.DataFrame(columns=SHEET_HEADERS.get(sn, []))
    return results


def _save_raw(sheet_name: str, df: pd.DataFrame, loc: str) -> None:
    """Internal: persist to Supabase + CSV without triggering derived-sheet updates.
    Always call this from update_derived_sheets() to avoid infinite recursion.
    """
    client = _get_supabase_client()
    if client is not None:
        try:
            table_name = _sheet_to_supabase_table(sheet_name)
            records = df.to_dict(orient="records")
            for r in records:
                r["location"] = loc
                # Remove the auto-generated serial 'id' column that Supabase adds.
                # If included on INSERT it causes primary-key conflicts and silent failures.
                r.pop("id", None)
                for k, v in list(r.items()):
                    if pd.isna(v):
                        r[k] = None
                    elif isinstance(v, (bool, int, float, str)):
                        pass
                    else:
                        r[k] = str(v)
            client.table(table_name).delete().eq("location", loc).execute()
            if records:
                client.table(table_name).insert(records).execute()
        except Exception as e:
            print(f"Supabase save failed for {sheet_name}: {e}")

    try:
        _ensure_data_dir(location=loc)
        df.to_csv(_csv_path(sheet_name, location=loc), index=False)
    except Exception:
        pass


def save_sheet(sheet_name: str, df: pd.DataFrame, _skip_derived: bool = False) -> None:
    """Save a sheet to Supabase (if configured) or fallback to its CSV file.

    Pass _skip_derived=True from within a pipeline of saves to defer the
    derived-sheet recomputation (Leaderboard, PlayerStats) to the very end.
    The cache is ALWAYS cleared so that subsequent load_sheet() calls within
    the same pipeline get fresh data — skipping this would cause stale reads
    that overwrite the records we just wrote.
    """
    loc = _get_location().lower()

    # Persist to Supabase + local CSV
    _save_raw(sheet_name, df, loc)

    # Always bust Streamlit caches so subsequent load_sheet() calls see fresh data.
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass

    # Update derived sheets (Leaderboard, PlayerStats) when source data changes.
    # Skip this if the caller will trigger it once at the end of a pipeline.
    if not _skip_derived and sheet_name in ("Players", "Teams", "Matches", "MatchStats"):
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
    Uses _save_raw() (not save_sheet()) to avoid infinite recursion.
    """
    _ensure_data_dir()
    loc = _get_location().lower()

    teams_df   = load_sheet("Teams")
    players_df = load_sheet("Players")
    ms_df      = load_sheet("MatchStats")
    matches_df = load_sheet("Matches")

    # ---- Leaderboard -------------------------------------------------------
    if teams_df.empty:
        pd.DataFrame(columns=SHEET_HEADERS["Leaderboard"]).to_csv(
            _csv_path("Leaderboard"), index=False
        )
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
            ["wins", "losses", "total_points"],
            ascending=[False, True, False],
        ).reset_index(drop=True)
        lb.insert(0, "rank", range(1, len(lb) + 1))
        lb = lb[["rank", "team_id", "team_name", "wins", "losses", "status", "total_points", "total_awards"]]

        _save_raw("Leaderboard", lb, loc)

    # ---- PlayerStats -------------------------------------------------------
    if players_df.empty:
        empty_ps = pd.DataFrame(columns=SHEET_HEADERS["PlayerStats"])
        _save_raw("PlayerStats", empty_ps, loc)
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
        _save_raw("PlayerStats", ps, loc)
