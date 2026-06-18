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
    try:
        import streamlit as st
        if "_location" in st.session_state:
            return st.session_state["_location"]
    except Exception:
        pass
    return getattr(_tls, "active_location", LOCATIONS[0])


def set_location(loc: str) -> None:
    """Switch active location for this thread only — other sessions are unaffected."""
    _tls.active_location = loc
    try:
        import streamlit as st
        st.session_state["_location"] = loc
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pipeline write cache
# ---------------------------------------------------------------------------
# Within a single save pipeline (record_result → save_match_awards), we do
# many sequential writes followed by reads of data we just wrote.  Without
# caching those writes in memory, every load_sheet call hits Supabase again
# (~450 ms each), adding 5+ seconds of pure network wait.
#
# _tls.pipeline_cache is a dict[(sheet_name_lower, loc_lower)] -> DataFrame
# that stores the last written DataFrame per table.  load_sheet consults it
# before going to Supabase/CSV.  It is cleared at the end of each top-level
# save_sheet call (the one that triggers update_derived_sheets).
# ---------------------------------------------------------------------------

def _pc_key(sheet_name: str, loc: str) -> tuple:
    return (sheet_name.lower(), loc.lower())


def _pc_put(sheet_name: str, loc: str, df: "pd.DataFrame") -> None:
    if not hasattr(_tls, "pipeline_cache"):
        _tls.pipeline_cache = {}
    _tls.pipeline_cache[_pc_key(sheet_name, loc)] = df.copy()


def _pc_get(sheet_name: str, loc: str) -> "pd.DataFrame | None":
    cache = getattr(_tls, "pipeline_cache", {})
    return cache.get(_pc_key(sheet_name, loc))


def _pc_clear() -> None:
    _tls.pipeline_cache = {}


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


_local_versions: dict[str, int] = {}


def _get_supabase_sync_version(loc_lower: str) -> int:
    client = _get_supabase_client()
    if client is None:
        return 1
    try:
        response = client.table("sync_state").select("version").eq("location", loc_lower).execute()
        data = response.data
        if data:
            return int(data[0]["version"])
    except Exception as e:
        print(f"Error fetching supabase sync version: {e}")
    return 1


try:
    import streamlit as _st
    _get_supabase_sync_version_cached = _st.cache_data(ttl=3, show_spinner=False)(_get_supabase_sync_version)
except Exception:
    _get_supabase_sync_version_cached = _get_supabase_sync_version


def get_sync_version(loc: str) -> int:
    """Return a version indicator that changes when the database/CSVs are updated."""
    loc_lower = loc.lower()
    client = _get_supabase_client()
    if client is not None:
        try:
            return _get_supabase_sync_version_cached(loc_lower)
        except Exception:
            pass

    # Fallback to local CSV modification time hash
    try:
        mtimes = []
        for sheet_name in SHEET_HEADERS:
            path = _csv_path(sheet_name, location=loc)
            if os.path.exists(path):
                mtimes.append(os.path.getmtime(path))
        if mtimes:
            return hash(tuple(mtimes))
    except Exception:
        pass

    return _local_versions.get(loc_lower, 1)


def _increment_sync_version(loc: str) -> None:
    """Increment the sync version for a location, both in local memory and in Supabase."""
    loc_lower = loc.lower()
    _local_versions[loc_lower] = _local_versions.get(loc_lower, 1) + 1

    client = _get_supabase_client()
    if client is not None:
        try:
            response = client.table("sync_state").select("version").eq("location", loc_lower).execute()
            data = response.data
            if data:
                new_version = int(data[0]["version"]) + 1
                client.table("sync_state").update({"version": new_version}).eq("location", loc_lower).execute()
            else:
                client.table("sync_state").insert({"location": loc_lower, "version": 1}).execute()
            
            # Clear the read cache so next get_sync_version call sees it instantly
            try:
                _get_supabase_sync_version_cached.clear()
            except Exception:
                pass
        except Exception as e:
            print(f"Failed to increment sync version for {loc}: {e}")


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


def _get_session_cache(sheet_name: str, loc: str) -> pd.DataFrame | None:
    try:
        import streamlit as st
        state = st.session_state
        cache_key = f"_db_cache_{loc.lower()}"
        if cache_key in state:
            cache = state[cache_key]
            # Check version
            current_version = get_sync_version(loc)
            if cache.get("version") == current_version:
                return cache.get("sheets", {}).get(sheet_name)
    except Exception:
        pass
    return None


def _put_session_cache(sheet_name: str, loc: str, df: pd.DataFrame) -> None:
    try:
        import streamlit as st
        state = st.session_state
        cache_key = f"_db_cache_{loc.lower()}"
        current_version = get_sync_version(loc)
        if cache_key not in state or state[cache_key].get("version") != current_version:
            state[cache_key] = {
                "version": current_version,
                "sheets": {}
            }
        state[cache_key]["sheets"][sheet_name] = df.copy()
    except Exception:
        pass


def load_sheet(sheet_name: str, location: str | None = None) -> pd.DataFrame:
    """Load a sheet from Supabase (if configured) or fallback to its CSV file."""
    loc = (location or _get_location()).lower()

    # 1. Check the pipeline write cache first — avoids redundant Supabase reads
    #    within a save pipeline (record_result, save_match_awards, etc.).
    cached = _pc_get(sheet_name, loc)
    if cached is not None:
        return cached

    # 2. Check the session-state version cache
    session_cached = _get_session_cache(sheet_name, loc)
    if session_cached is not None:
        return session_cached

    # 3. Try Supabase
    supabase_df = _load_from_supabase(sheet_name, loc)
    if supabase_df is not None:
        _put_session_cache(sheet_name, loc, supabase_df)
        return supabase_df

    # 4. Fallback to local CSV
    _ensure_data_dir(location)
    expected_cols = SHEET_HEADERS.get(sheet_name, [])
    path = _csv_path(sheet_name, location)

    if not os.path.exists(path):
        empty_df = pd.DataFrame(columns=expected_cols)
        _put_session_cache(sheet_name, loc, empty_df)
        return empty_df

    df = _load_csv_from_path(path, sheet_name)
    _put_session_cache(sheet_name, loc, df)
    return df


def load_sheets(sheet_names: list[str], location: str | None = None) -> dict[str, pd.DataFrame]:
    """Load multiple sheets in parallel using a thread pool to optimize load times.

    Returns a dict mapping sheet_name -> DataFrame.
    """
    import concurrent.futures
    loc = location or _get_location()

    results = {}
    remaining_sheets = []

    # Check cache first on the main thread
    for sn in sheet_names:
        cached = _pc_get(sn, loc)
        if cached is None:
            cached = _get_session_cache(sn, loc)
        if cached is not None:
            results[sn] = cached
        else:
            remaining_sheets.append(sn)

    if not remaining_sheets:
        return results

    # Load remaining sheets in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(remaining_sheets), 6)) as executor:
        futures = {executor.submit(load_sheet, sn, loc): sn for sn in remaining_sheets}
        for future in concurrent.futures.as_completed(futures):
            sn = futures[future]
            try:
                df = future.result()
                results[sn] = df
                _put_session_cache(sn, loc, df)
            except Exception as e:
                print(f"Parallel load failed for {sn}: {e}")
                results[sn] = pd.DataFrame(columns=SHEET_HEADERS.get(sn, []))
    return results


def _save_raw(sheet_name: str, df: pd.DataFrame, loc: str) -> None:
    """Internal: persist to Supabase + CSV without triggering derived-sheet updates.
    Always call this from update_derived_sheets() to avoid infinite recursion.
    Also stores the written df in the pipeline cache so subsequent load_sheet
    calls within the same pipeline get instant in-memory results.
    """
    # Store in pipeline cache immediately so reads within this pipeline are instant
    _pc_put(sheet_name, loc, df)

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
                    if v is None:
                        continue
                    try:
                        if pd.isna(v):
                            r[k] = None
                            continue
                    except (TypeError, ValueError):
                        pass
                    # Pandas reads integer columns containing NaN as float64 from CSV
                    # (e.g. 5.0 instead of 5). Supabase integer columns reject "5.0"
                    # strings, so we must convert whole floats to int.
                    if isinstance(v, float) and v == int(v):
                        r[k] = int(v)
                    elif not isinstance(v, (bool, int, float, str)):
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

    _increment_sync_version(loc)


def save_sheet(sheet_name: str, df: pd.DataFrame, _skip_derived: bool = False) -> None:
    """Save a sheet to Supabase (if configured) or fallback to its CSV file.

    Pass _skip_derived=True from within a pipeline of saves to defer the
    derived-sheet recomputation (Leaderboard, PlayerStats) to the very end.
    The cache is ALWAYS cleared so that subsequent load_sheet() calls within
    the same pipeline get fresh data from Supabase when the pipeline cache
    doesn't have a newer version.
    """
    loc = _get_location().lower()

    # Persist to Supabase + local CSV (also stores in pipeline cache)
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
        # Clear the pipeline cache once the full pipeline is done so the next
        # page load reads fresh state from Supabase.
        _pc_clear()


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
            ["total_points", "wins", "losses"],
            ascending=[False, False, True],
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
