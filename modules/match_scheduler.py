"""
match_scheduler.py  —  Phase 3
Generates the full double-elimination bracket from the teams list.

Bracket logic:
  Round 1  : All teams randomly drawn into head-to-head pairs (Winners bracket).
  After R1 : Winners stay in Winners bracket; losers drop to Losers bracket.
  Losers bracket: Each team gets exactly ONE rematch. Win it → re-enter main pool.
                  Lose it (2 losses total) → eliminated. No further losers matches.
  Finals   : Last 2 active teams meet. Single match — no rematch.
             The winner is champion; the loser is eliminated immediately.

advance_bracket() is called automatically by match_recorder after every result.
"""

import random
import pandas as pd
from datetime import date
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
            "scheduled_date": None,
            "scheduled_time": None,
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


def _choose_bye(df_group: pd.DataFrame) -> int | None:
    if df_group.empty:
        return None
    # Prefer team with highest wins, then highest avg_skill, then lowest team_id
    df = df_group.copy()
    df["wins"] = pd.to_numeric(df.get("wins", 0), errors="coerce").fillna(0).astype(int)
    df["avg_skill"] = pd.to_numeric(df.get("avg_skill", 0), errors="coerce").fillna(0)
    df = df.sort_values(["wins", "avg_skill", "team_id"], ascending=[False, False, True])
    return int(df.iloc[0]["team_id"])


def advance_bracket(completed_match_id: int) -> None:
    """
    Called after a match result is recorded. Inspects the current bracket
    state and creates the next scheduled match(es) in the next round
    if all matches of the current round are completed.
    """
    matches_df = load_sheet("Matches")
    teams_df   = load_sheet("Teams")

    # If there are any pending (scheduled/in_progress) matches, we wait and do not advance.
    # Note: 'bye' matches are already 'done' so they are not pending.
    pending = matches_df[matches_df["status"].isin(["scheduled", "in_progress"])]
    if not pending.empty:
        return

    # All active matches are completed. Let's see who is still active.
    active = teams_df[~teams_df["is_eliminated"].apply(_is_eliminated)].copy()
    active["losses"] = pd.to_numeric(active["losses"], errors="coerce").fillna(0).astype(int)

    if len(active) <= 1:
        return  # Tournament complete - champion determined!

    done = matches_df[matches_df["status"] == "done"]
    next_round = int(done["round"].max()) + 1 if not done.empty else 1

    # If a Finals match has already been played, the tournament is over.
    # The Finals is a single definitive match — no rematch.
    # Eliminate the loser unconditionally (they may only have 1 loss if they
    # were undefeated going in, so recalculate_team_stats won't catch them).
    finals_done = matches_df[
        (matches_df["bracket"] == "finals") &
        (matches_df["status"] == "done")
    ]
    if not finals_done.empty:
        last_final = finals_done.sort_values("match_id").iloc[-1]
        loser_id = last_final.get("loser_id")
        if pd.notna(loser_id):
            loser_id = int(loser_id)
            loser_row = teams_df[teams_df["team_id"] == loser_id]
            if not loser_row.empty and not _is_eliminated(loser_row.iloc[0]["is_eliminated"]):
                teams_df.loc[teams_df["team_id"] == loser_id, "is_eliminated"] = True
                save_sheet("Teams", teams_df, _skip_derived=True)
        return  # Tournament complete — no further matches.

    undefeated = active[active["losses"] == 0].reset_index(drop=True)
    one_loss   = active[active["losses"] == 1].reset_index(drop=True)

    # Check if we are in the Finals (1 undefeated, 1 one-loss)
    if len(undefeated) == 1 and len(one_loss) == 1:
        # Check if we have already scheduled a finals match for this round
        finals_scheduled = matches_df[
            (matches_df["bracket"] == "finals") &
            (matches_df["round"] == next_round)
        ]
        if finals_scheduled.empty:
            new_matches = [_make_match(
                match_id=get_next_id("Matches", "match_id"),
                round_num=next_round,
                team_a_id=int(undefeated.iloc[0]["team_id"]),
                team_b_id=int(one_loss.iloc[0]["team_id"]),
                bracket="finals",
            )]
            updated = pd.concat([matches_df, pd.DataFrame(new_matches)], ignore_index=True)
            save_sheet("Matches", updated, _skip_derived=True)
        return

    # Otherwise, we have a normal bracket round
    new_matches = []
    base_id = get_next_id("Matches", "match_id")

    # 1. Winners Bracket Pairing (undefeated teams)
    w_teams = list(undefeated["team_id"].astype(int))
    for i in range(0, len(w_teams) - 1, 2):
        new_matches.append(_make_match(
            match_id=base_id + len(new_matches),
            round_num=next_round,
            team_a_id=w_teams[i],
            team_b_id=w_teams[i + 1],
            bracket="winners",
        ))

    # If odd number of undefeated teams, choose one to get a bye
    if len(w_teams) % 2 == 1:
        bye_team = _choose_bye(undefeated)
        if bye_team is not None:
            new_matches.append({
                "match_id": base_id + len(new_matches),
                "round": next_round,
                "team_a_id": bye_team,
                "team_b_id": None,
                "winner_id": bye_team,
                "loser_id": None,
                "bracket": "winners",
                "status": "bye",
                "scheduled_date": None,
                "scheduled_time": None,
                "date_played": None,
                "team_a_score": None,
                "team_b_score": None,
            })
            # Grant bye win
            teams_df.loc[teams_df["team_id"] == bye_team, "wins"] = (
                teams_df.loc[teams_df["team_id"] == bye_team, "wins"].fillna(0).astype(int) + 1
            )

    # 2. Losers Bracket Pairing (1-loss teams)
    l_teams = list(one_loss["team_id"].astype(int))
    for i in range(0, len(l_teams) - 1, 2):
        new_matches.append(_make_match(
            match_id=base_id + len(new_matches),
            round_num=next_round,
            team_a_id=l_teams[i],
            team_b_id=l_teams[i + 1],
            bracket="losers",
        ))

    # If odd number of 1-loss teams, choose one to get a bye
    if len(l_teams) % 2 == 1:
        bye_team = _choose_bye(one_loss)
        if bye_team is not None:
            new_matches.append({
                "match_id": base_id + len(new_matches),
                "round": next_round,
                "team_a_id": bye_team,
                "team_b_id": None,
                "winner_id": bye_team,
                "loser_id": None,
                "bracket": "losers",
                "status": "bye",
                "scheduled_date": None,
                "scheduled_time": None,
                "date_played": None,
                "team_a_score": None,
                "team_b_score": None,
            })
            # Grant bye win
            teams_df.loc[teams_df["team_id"] == bye_team, "wins"] = (
                teams_df.loc[teams_df["team_id"] == bye_team, "wins"].fillna(0).astype(int) + 1
            )

    if new_matches:
        save_sheet("Teams", teams_df, _skip_derived=True)
        updated = pd.concat([matches_df, pd.DataFrame(new_matches)], ignore_index=True)
        save_sheet("Matches", updated, _skip_derived=True)


def schedule_finals_by_points() -> None:
    """Trigger the bracket advancement checks to see if finals can be scheduled."""
    advance_bracket(0)


def get_schedule() -> pd.DataFrame:
    """Return the full match schedule."""
    return load_sheet("Matches")


def set_match_scheduled_date(match_id: int, scheduled_date) -> None:
    """Set or clear the planned date for a scheduled match.

    *scheduled_date* may be a datetime.date, an ISO string (YYYY-MM-DD),
    or None to clear the date.
    """
    df = load_sheet("Matches")
    if df.empty or match_id not in df["match_id"].astype(int).values:
        raise ValueError(f"Match ID {match_id} not found.")
    if scheduled_date is not None:
        val = str(scheduled_date)  # date.isoformat() or already a string
    else:
        val = None
    df["scheduled_date"] = df["scheduled_date"].astype(object)
    df["scheduled_time"] = df.get("scheduled_time", None).astype(object)
    df.loc[df["match_id"].astype(int) == match_id, "scheduled_date"] = val
    save_sheet("Matches", df)


def set_match_scheduled_time(match_id: int, scheduled_time) -> None:
    """Set or clear the planned time for a scheduled match.

    *scheduled_time* may be a time object, a string "HH:MM", or None to clear.
    """
    df = load_sheet("Matches")
    if df.empty or match_id not in df["match_id"].astype(int).values:
        raise ValueError(f"Match ID {match_id} not found.")
    if scheduled_time is not None:
        # Normalize to HH:MM string
        try:
            st = str(scheduled_time)
            if hasattr(scheduled_time, "strftime"):
                st = scheduled_time.strftime("%H:%M")
        except Exception:
            st = str(scheduled_time)
        val = st
    else:
        val = None
    df["scheduled_time"] = df.get("scheduled_time", None).astype(object)
    df.loc[df["match_id"].astype(int) == match_id, "scheduled_time"] = val
    save_sheet("Matches", df)


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
        "winner_id", "loser_id", "bracket", "status", "scheduled_date", "scheduled_time", "date_played",
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
        "scheduled_date": None,
        "scheduled_time": None,
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

