"""
match_scheduler.py  —  Phase 3
Generates the full double-elimination bracket from the teams list.

Bracket logic:
  Round 1  : All teams randomly drawn into head-to-head pairs (Winners bracket).
  After R1 : Winners stay in Winners bracket; losers drop to Losers bracket.
  Losers bracket: Each team gets exactly ONE rematch. Win it → re-enter main pool.
                  Lose it (2 losses total) → eliminated. No further losers matches.
  Finals   : Last 2 active teams meet.

advance_bracket() is called automatically by match_recorder after every result.
"""

import random
import pandas as pd
from modules.excel_sync import load_sheet, save_sheet, get_next_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_schedule() -> pd.DataFrame:
    """
    Generate Round 1 matches with a random bracket draw.
    Each team is randomly shuffled, then paired sequentially.
    If the team count is odd, the last team receives a bye (auto-win, no loser).

    Raises RuntimeError if schedule already exists or fewer than 2 teams.
    Returns the Matches DataFrame.
    """
    existing = load_sheet("Matches")
    if not existing.empty:
        raise RuntimeError("Schedule already generated. Reset matches to regenerate.")

    teams_df = load_sheet("Teams")
    if teams_df.empty or len(teams_df) < 2:
        raise RuntimeError("At least 2 teams are required to generate a schedule.")

    team_ids = teams_df["team_id"].astype(int).tolist()
    random.shuffle(team_ids)

    new_matches = []
    base_id = get_next_id("Matches", "match_id")
    offset = 0

    i = 0
    while i + 1 < len(team_ids):
        new_matches.append(_make_match(
            match_id=base_id + offset,
            round_num=1,
            team_a_id=team_ids[i],
            team_b_id=team_ids[i + 1],
            bracket="winners",
        ))
        offset += 1
        i += 2

    # Odd team out → auto-bye (win with no match played)
    if i < len(team_ids):
        bye_id = team_ids[i]
        new_matches.append({
            "match_id":   base_id + offset,
            "round":      1,
            "team_a_id":  bye_id,
            "team_b_id":  None,
            "winner_id":  bye_id,
            "loser_id":   None,
            "bracket":    "winners",
            "status":     "bye",
            "date_played": None,
        })
        # Grant the bye win
        teams_df.loc[teams_df["team_id"] == bye_id, "wins"] = (
            teams_df.loc[teams_df["team_id"] == bye_id, "wins"].fillna(0).astype(int) + 1
        )
        save_sheet("Teams", teams_df)

    matches_df = pd.DataFrame(new_matches)
    save_sheet("Matches", matches_df)
    return matches_df


def advance_bracket(completed_match_id: int) -> None:
    """
    Called after a match result is recorded. Inspects the current bracket
    state and creates the next scheduled match(es) as appropriate:
      - 2+ winners-bracket teams free  → pair them in a winners match
      - 2+ losers-bracket teams free   → pair them in a losers match
      - exactly 1 winner + 1 loser, only 2 teams remain → finals
    """
    matches_df = load_sheet("Matches")
    teams_df   = load_sheet("Teams")

    # Active (non-eliminated) teams
    active = teams_df[~teams_df["is_eliminated"].apply(_is_eliminated)].copy()
    active["losses"] = pd.to_numeric(active["losses"], errors="coerce").fillna(0).astype(int)

    if len(active) <= 1:
        return  # tournament over

    # Teams currently in a scheduled or in-progress match
    pending = matches_df[matches_df["status"].isin(["scheduled", "in_progress"])]
    if not pending.empty:
        busy_ids = set(
            list(pending["team_a_id"].dropna().astype(int))
            + list(pending["team_b_id"].dropna().astype(int))
        )
    else:
        busy_ids = set()

    free = active[~active["team_id"].isin(busy_ids)].copy()

    if len(free) < 2:
        return  # not enough free teams yet

    done = matches_df[matches_df["status"] == "done"]
    next_round = int(done["round"].max()) + 1 if not done.empty else 1

    # Finals: only 2 active teams and both are free
    if len(active) == 2 and len(free) == 2:
        t1 = int(free.iloc[0]["team_id"])
        t2 = int(free.iloc[1]["team_id"])
        _append_match(_make_match(
            match_id=get_next_id("Matches", "match_id"),
            round_num=next_round,
            team_a_id=t1,
            team_b_id=t2,
            bracket="finals",
        ))
        return

    # Teams that have already won a losers-bracket match have used their one rematch.
    # They re-enter the main pool and are NOT eligible for another losers match.
    used_rematch_ids = set(
        matches_df[
            (matches_df["status"] == "done") &
            (matches_df["bracket"] == "losers")
        ]["winner_id"].dropna().astype(int).tolist()
    )

    # Main pool: undefeated teams + rematch survivors (1 loss, used their rematch)
    w_free = free[
        (free["losses"] == 0) | (free["team_id"].isin(used_rematch_ids))
    ].reset_index(drop=True)

    # Losers bracket: only teams with exactly 1 loss who have NOT yet had their rematch
    l_free = free[
        (free["losses"] == 1) & (~free["team_id"].isin(used_rematch_ids))
    ].reset_index(drop=True)

    new_matches = []
    base_id = get_next_id("Matches", "match_id")

    for i in range(0, len(w_free) - 1, 2):
        new_matches.append(_make_match(
            match_id=base_id + len(new_matches),
            round_num=next_round,
            team_a_id=int(w_free.iloc[i]["team_id"]),
            team_b_id=int(w_free.iloc[i + 1]["team_id"]),
            bracket="winners",
        ))

    for i in range(0, len(l_free) - 1, 2):
        new_matches.append(_make_match(
            match_id=base_id + len(new_matches),
            round_num=next_round,
            team_a_id=int(l_free.iloc[i]["team_id"]),
            team_b_id=int(l_free.iloc[i + 1]["team_id"]),
            bracket="losers",
        ))

    if new_matches:
        current = load_sheet("Matches")
        updated = pd.concat([current, pd.DataFrame(new_matches)], ignore_index=True)
        save_sheet("Matches", updated)


def get_schedule() -> pd.DataFrame:
    """Return the full match schedule."""
    return load_sheet("Matches")


def reset_schedule() -> None:
    """
    Wipe all match data and reset team win/loss counters.
    Only call this if you want to regenerate the bracket from scratch.
    """
    teams_df = load_sheet("Teams")
    if not teams_df.empty:
        teams_df["wins"]         = 0
        teams_df["losses"]       = 0
        teams_df["is_eliminated"] = False
        save_sheet("Teams", teams_df)

    save_sheet("Matches", pd.DataFrame(columns=[
        "match_id", "round", "team_a_id", "team_b_id",
        "winner_id", "loser_id", "bracket", "status", "date_played",
    ]))

    save_sheet("MatchStats", pd.DataFrame(columns=[
        "stat_id", "match_id", "player_id", "team_id",
        "queen_snatcher", "precision_player",
        "best_striker", "comeback_king",
    ]))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _make_match(match_id: int, round_num: int, team_a_id: int,
                team_b_id: int, bracket: str) -> dict:
    return {
        "match_id":    match_id,
        "round":       round_num,
        "team_a_id":   team_a_id,
        "team_b_id":   team_b_id,
        "winner_id":   None,
        "loser_id":    None,
        "bracket":     bracket,
        "status":      "scheduled",
        "date_played": None,
    }


def _append_match(match: dict) -> None:
    current = load_sheet("Matches")
    updated = pd.concat([current, pd.DataFrame([match])], ignore_index=True)
    save_sheet("Matches", updated)


def _is_eliminated(val) -> bool:
    return val is True or val == 1 or str(val).lower() == "true"

