"""
match_recorder.py  —  Phase 4
Records match results (win/loss) and per-player per-match award flags.

Awards are boolean (0/1) and assigned by the umpire after each match.
Multiple players can hold different awards in the same match.

Flow:
  1. record_result(match_id, winner_team_id)
       → updates Matches, Teams (wins/losses, elimination)
       → calls match_scheduler.advance_bracket() to create next match
  2. save_match_awards(match_id, award_map)
       → upserts rows in MatchStats
"""

import pandas as pd
from datetime import date
from modules.excel_sync import load_sheet, save_sheet, get_next_id, AWARDS


def record_result(
    match_id: int,
    winner_team_id: int,
    team_a_score: int = 0,
    team_b_score: int = 0,
) -> None:
    """
    Set the winner/loser for a match, mark it as 'done',
    record team scores, update team win/loss counters,
    eliminate teams with 2 losses, then advance the bracket.

    team_a_score / team_b_score are piece-only totals; the queen bonus
    (+5, capped at 24) is applied separately in save_match_awards.

    Raises ValueError if the match is not found or already completed.
    """
    matches_df = load_sheet("Matches")

    mask = matches_df["match_id"] == match_id
    if not mask.any():
        raise ValueError(f"Match ID {match_id} not found.")

    row = matches_df.loc[mask].iloc[0]
    if str(row["status"]) in ("done", "bye"):
        raise ValueError(f"Match {match_id} is already completed.")

    team_a = int(row["team_a_id"])
    team_b = int(row["team_b_id"])

    if winner_team_id not in (team_a, team_b):
        raise ValueError(
            f"Winner ID {winner_team_id} is not a participant in match {match_id}."
        )

    loser_team_id = team_b if winner_team_id == team_a else team_a

    # Update match record — cast columns to correct dtypes before writing
    matches_df["winner_id"]    = pd.to_numeric(matches_df["winner_id"],    errors="coerce")
    matches_df["loser_id"]     = pd.to_numeric(matches_df["loser_id"],     errors="coerce")
    matches_df["team_a_score"] = pd.to_numeric(matches_df.get("team_a_score", 0), errors="coerce").fillna(0)
    matches_df["team_b_score"] = pd.to_numeric(matches_df.get("team_b_score", 0), errors="coerce").fillna(0)
    matches_df["date_played"]  = matches_df["date_played"].astype(object)
    matches_df.loc[mask, "winner_id"]    = winner_team_id
    matches_df.loc[mask, "loser_id"]     = loser_team_id
    matches_df.loc[mask, "status"]       = "done"
    matches_df.loc[mask, "date_played"]  = str(date.today())
    matches_df.loc[mask, "team_a_score"] = int(team_a_score)
    matches_df.loc[mask, "team_b_score"] = int(team_b_score)
    save_sheet("Matches", matches_df)

    # Update team stats
    teams_df = load_sheet("Teams")
    teams_df["wins"]   = pd.to_numeric(teams_df["wins"],   errors="coerce").fillna(0).astype(int)
    teams_df["losses"] = pd.to_numeric(teams_df["losses"], errors="coerce").fillna(0).astype(int)

    teams_df.loc[teams_df["team_id"] == winner_team_id, "wins"]   += 1
    teams_df.loc[teams_df["team_id"] == loser_team_id,  "losses"] += 1

    # Finals = winner takes all: loser out, winner un-eliminated (champion, even if from pool elimination)
    is_finals = str(row["bracket"]).lower() == "finals"
    if is_finals:
        teams_df.loc[teams_df["team_id"] == loser_team_id,  "is_eliminated"] = True
        teams_df.loc[teams_df["team_id"] == winner_team_id, "is_eliminated"] = False
    else:
        # Eliminate loser if they now have 2 losses
        loser_losses = int(
            teams_df.loc[teams_df["team_id"] == loser_team_id, "losses"].iloc[0]
        )
        if loser_losses >= 2:
            teams_df.loc[teams_df["team_id"] == loser_team_id, "is_eliminated"] = True

    save_sheet("Teams", teams_df)

    # Do not advance bracket after finals — tournament is over
    if is_finals:
        return

    # Advance bracket (import here to avoid circular imports at module level)
    from modules.match_scheduler import advance_bracket
    advance_bracket(match_id)


def save_match_awards(match_id: int, award_map: dict) -> None:
    """
    Save per-player award flags for a match.

    award_map: {
        player_id (int): {
            "queen_snatcher":   0|1,
            "precision_player": 0|1,
            "best_striker":     0|1,
            "comeback_king":    0|1,
        }
    }
    Upserts rows in the MatchStats sheet (one row per player per match).
    Replaces any existing entries for this match.
    """
    ms_df     = load_sheet("MatchStats")
    players_df = load_sheet("Players")

    # Remove existing entries for this match so we do a clean upsert
    if not ms_df.empty:
        ms_df = ms_df[ms_df["match_id"] != match_id].reset_index(drop=True)

    # Build player→team_id map
    pid_to_tid = {}
    if not players_df.empty:
        pid_to_tid = players_df.dropna(subset=["player_id"]).set_index(
            players_df["player_id"].astype(int)
        )["team_id"].to_dict()

    new_rows = []
    base_stat_id = get_next_id("MatchStats", "stat_id")
    for offset, (player_id, awards) in enumerate(award_map.items()):
        row = {
            "stat_id":  base_stat_id + offset,
            "match_id": match_id,
            "player_id": int(player_id),
            "team_id":   pid_to_tid.get(int(player_id)),
        }
        for award in AWARDS:
            row[award] = int(bool(awards.get(award, 0)))
        new_rows.append(row)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        ms_df  = pd.concat([ms_df, new_df], ignore_index=True)

    save_sheet("MatchStats", ms_df)

    # Apply queen snatcher bonus: +5 points to the snatcher's team, capped at 24
    queen_pid = next(
        (pid for pid, a in award_map.items() if a.get("queen_snatcher", 0)),
        None,
    )
    if queen_pid is not None and not players_df.empty:
        player_row = players_df[players_df["player_id"] == int(queen_pid)]
        if not player_row.empty:
            queen_team_id = int(player_row.iloc[0]["team_id"])
            matches_df = load_sheet("Matches")
            m_mask = matches_df["match_id"] == match_id
            if m_mask.any():
                matches_df["team_a_score"] = pd.to_numeric(
                    matches_df["team_a_score"], errors="coerce"
                ).fillna(0).astype(int)
                matches_df["team_b_score"] = pd.to_numeric(
                    matches_df["team_b_score"], errors="coerce"
                ).fillna(0).astype(int)
                team_a_id = int(matches_df.loc[m_mask, "team_a_id"].iloc[0])
                if queen_team_id == team_a_id:
                    raw = int(matches_df.loc[m_mask, "team_a_score"].iloc[0])
                    matches_df.loc[m_mask, "team_a_score"] = min(raw + 5, 24)
                else:
                    raw = int(matches_df.loc[m_mask, "team_b_score"].iloc[0])
                    matches_df.loc[m_mask, "team_b_score"] = min(raw + 5, 24)
                save_sheet("Matches", matches_df)


def get_match_awards(match_id: int) -> pd.DataFrame:
    """Return MatchStats rows for a specific match."""
    ms = load_sheet("MatchStats")
    if ms.empty:
        return ms
    return ms[ms["match_id"] == match_id].reset_index(drop=True)


def edit_match_result(
    match_id: int,
    team_a_score: int,
    team_b_score: int,
    award_map: dict,
) -> None:
    """
    Correct scores and awards for an already-completed match.
    Scores are written directly — no queen bonus is re-applied.
    All existing award entries for this match are replaced.
    """
    matches_df = load_sheet("Matches")
    mask = matches_df["match_id"] == match_id
    if not mask.any():
        raise ValueError(f"Match ID {match_id} not found.")
    if str(matches_df.loc[mask].iloc[0]["status"]) != "done":
        raise ValueError(f"Match {match_id} is not completed — use the record form instead.")

    matches_df["team_a_score"] = pd.to_numeric(
        matches_df.get("team_a_score", 0), errors="coerce"
    ).fillna(0).astype(int)
    matches_df["team_b_score"] = pd.to_numeric(
        matches_df.get("team_b_score", 0), errors="coerce"
    ).fillna(0).astype(int)
    matches_df.loc[mask, "team_a_score"] = max(0, min(int(team_a_score), 24))
    matches_df.loc[mask, "team_b_score"] = max(0, min(int(team_b_score), 24))
    save_sheet("Matches", matches_df)

    if award_map:
        ms_df      = load_sheet("MatchStats")
        players_df = load_sheet("Players")
        if not ms_df.empty:
            ms_df = ms_df[ms_df["match_id"] != match_id].reset_index(drop=True)

        pid_to_tid: dict = {}
        if not players_df.empty:
            pid_to_tid = players_df.dropna(subset=["player_id"]).set_index(
                players_df["player_id"].astype(int)
            )["team_id"].to_dict()

        new_rows = []
        base_stat_id = get_next_id("MatchStats", "stat_id")
        for offset, (player_id, awards) in enumerate(award_map.items()):
            row = {
                "stat_id":   base_stat_id + offset,
                "match_id":  match_id,
                "player_id": int(player_id),
                "team_id":   pid_to_tid.get(int(player_id)),
            }
            for award in AWARDS:
                row[award] = int(bool(awards.get(award, 0)))
            new_rows.append(row)

        if new_rows:
            ms_df = pd.concat([ms_df, pd.DataFrame(new_rows)], ignore_index=True)
        save_sheet("MatchStats", ms_df)

