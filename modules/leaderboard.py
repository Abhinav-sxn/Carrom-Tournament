"""
leaderboard.py  —  Phase 5
Read-only helpers that pull from the pre-computed Leaderboard
and PlayerStats sheets (both maintained by excel_sync.update_derived_sheets).
"""

import pandas as pd
from modules.excel_sync import load_sheet, AWARDS


def get_team_standings() -> pd.DataFrame:
    """Return the Leaderboard sheet as a DataFrame."""
    return load_sheet("Leaderboard")


def get_player_stats() -> pd.DataFrame:
    """Return the PlayerStats sheet as a DataFrame."""
    return load_sheet("PlayerStats")


def get_award_leaders() -> dict:
    """
    Return a dict mapping each award name to the top player's name and count.
    E.g. { "silent_assassin": {"name": "Alice", "count": 3}, ... }
    """
    ps = load_sheet("PlayerStats")
    leaders = {}
    if ps.empty:
        return {a: {"name": "—", "count": 0} for a in AWARDS}

    for award in AWARDS:
        if award in ps.columns and ps[award].sum() > 0:
            idx = ps[award].idxmax()
            leaders[award] = {
                "name":  ps.loc[idx, "name"],
                "count": int(ps.loc[idx, award]),
            }
        else:
            leaders[award] = {"name": "—", "count": 0}

    return leaders
