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

    # Only 2 active teams remain — finals are triggered manually via schedule_finals_by_points()
    if len(active) == 2:
        return

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

    # Auto-schedule finals once every pool match is complete
    refreshed   = load_sheet("Matches")
    pool        = refreshed[refreshed["bracket"].str.lower().isin(["winners", "losers"])]
    finals_set  = (refreshed["bracket"].str.lower() == "finals").any()
    pool_played = not pool.empty and (pool["status"] == "done").any()
    pool_clear  = pool_played and not (pool["status"] == "scheduled").any()
    if pool_clear and not finals_set:
        try:
            schedule_finals_by_points()
        except RuntimeError:
            pass


def schedule_finals_by_points() -> None:
    """
    Schedule the championship finals between the top 2 teams by total points
    accumulated across ALL pool matches (including eliminated teams).
    Wins are used as tiebreaker when points are equal.

    Raises RuntimeError if finals already scheduled or fewer than 2 teams have scores.
    """
    matches_df = load_sheet("Matches")
    teams_df   = load_sheet("Teams")

    if not matches_df.empty:
        if (matches_df["bracket"].str.lower() == "finals").any():
            raise RuntimeError("Finals already scheduled.")

    done_m = matches_df[matches_df["status"] == "done"].copy() if not matches_df.empty else pd.DataFrame()

    if done_m.empty:
        raise RuntimeError("No completed matches yet — cannot determine top 2 by points.")

    done_m["team_a_score"] = pd.to_numeric(done_m["team_a_score"], errors="coerce").fillna(0)
    done_m["team_b_score"] = pd.to_numeric(done_m["team_b_score"], errors="coerce").fillna(0)

    team_points: dict[int, int] = {}
    for _, row in done_m.iterrows():
        ta = int(row["team_a_id"]) if pd.notna(row["team_a_id"]) else None
        tb = int(row["team_b_id"]) if pd.notna(row["team_b_id"]) else None
        if ta is not None:
            team_points[ta] = team_points.get(ta, 0) + int(row["team_a_score"])
        if tb is not None:
            team_points[tb] = team_points.get(tb, 0) + int(row["team_b_score"])

    if len(team_points) < 2:
        raise RuntimeError("At least 2 teams must have played to schedule finals.")

    team_wins: dict[int, int] = {}
    if not teams_df.empty:
        for _, row in teams_df.iterrows():
            team_wins[int(row["team_id"])] = int(pd.to_numeric(row.get("wins", 0), errors="coerce") or 0)

    sorted_teams = sorted(
        team_points.keys(),
        key=lambda tid: (team_points[tid], team_wins.get(tid, 0)),
        reverse=True,
    )
    t1, t2 = sorted_teams[0], sorted_teams[1]

    next_round = int(done_m["round"].max()) + 1
    _append_match(_make_match(
        match_id=get_next_id("Matches", "match_id"),
        round_num=next_round,
        team_a_id=t1,
        team_b_id=t2,
        bracket="finals",
    ))


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
        "team_a_score", "team_b_score",
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
        "match_id":     match_id,
        "round":        round_num,
        "team_a_id":    team_a_id,
        "team_b_id":    team_b_id,
        "winner_id":    None,
        "loser_id":     None,
        "bracket":      bracket,
        "status":       "scheduled",
        "date_played":  None,
        "team_a_score": None,
        "team_b_score": None,
    }


def _append_match(match: dict) -> None:
    current = load_sheet("Matches")
    updated = pd.concat([current, pd.DataFrame([match])], ignore_index=True)
    save_sheet("Matches", updated)


def _is_eliminated(val) -> bool:
    return val is True or val == 1 or str(val).lower() == "true"

