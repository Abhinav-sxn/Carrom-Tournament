"""
team_builder.py  —  Phase 2
Balanced team pairing algorithm + team naming.

Algorithm (sorted interleaving):
  1. Sort players by skill_rating descending.
  2. Pair player[0] with player[N-1], player[1] with player[N-2], etc.
  3. Each pair forms a 2-player team — averages are naturally equalised.
  4. Organiser reviews averages, optionally assigns team names, then locks.
"""

import pandas as pd
from modules.excel_sync import load_sheet, save_sheet, get_next_id
from modules.player_manager import update_player_team


def build_balanced_teams() -> pd.DataFrame:
    """
    Read players from the Players sheet, run the pairing algorithm,
    create Team records, assign player team_ids, and save both sheets.
    Returns the Teams DataFrame.

    Raises:
        RuntimeError  if teams already exist, or player count < 4, or player
                      count is not even.
    """
    existing_teams = load_sheet("Teams")
    if not existing_teams.empty:
        raise RuntimeError(
            "Teams have already been built. Reset teams first to rebuild."
        )

    players_df = load_sheet("Players")
    if players_df.empty or len(players_df) < 4:
        raise RuntimeError("At least 4 players are required to form teams.")
    if len(players_df) % 2 != 0:
        raise RuntimeError(
            f"An even number of players is required for 2v2 teams. "
            f"Currently {len(players_df)} players registered."
        )

    # Sort descending by skill
    sorted_players = (
        players_df
        .sort_values("skill_rating", ascending=False)
        .reset_index(drop=True)
    )

    n = len(sorted_players)
    teams = []
    for i in range(n // 2):
        p1 = sorted_players.iloc[i]
        p2 = sorted_players.iloc[n - 1 - i]
        avg = round((float(p1["skill_rating"]) + float(p2["skill_rating"])) / 2, 2)
        team_id = get_next_id("Teams", "team_id") + i
        teams.append({
            "team_id":      team_id,
            "team_name":    f"Team {_num_to_letter(i)}",
            "avg_skill":    avg,
            "wins":         0,
            "losses":       0,
            "is_eliminated": False,
        })

    teams_df = pd.DataFrame(teams)
    save_sheet("Teams", teams_df)

    # Assign team_ids back to players (without triggering update_derived_sheets
    # each iteration — bulk update instead)
    players_copy = players_df.copy()
    for idx, team in enumerate(teams):
        p1_id = int(sorted_players.iloc[idx]["player_id"])
        p2_id = int(sorted_players.iloc[n - 1 - idx]["player_id"])
        players_copy.loc[players_copy["player_id"] == p1_id, "team_id"] = team["team_id"]
        players_copy.loc[players_copy["player_id"] == p2_id, "team_id"] = team["team_id"]

    save_sheet("Players", players_copy)
    return teams_df


def rename_team(team_id: int, new_name: str) -> None:
    """Update a team's display name."""
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Team name cannot be empty.")

    df = load_sheet("Teams")
    if df.empty or team_id not in df["team_id"].values:
        raise ValueError(f"Team ID {team_id} not found.")

    # Prevent duplicate names (case-insensitive), ignoring own row
    other_names = df.loc[df["team_id"] != team_id, "team_name"].str.lower()
    if new_name.lower() in other_names.values:
        raise ValueError(f'A team named "{new_name}" already exists.')

    df.loc[df["team_id"] == team_id, "team_name"] = new_name
    save_sheet("Teams", df)


def reset_teams() -> None:
    """
    Wipe all teams and clear player team assignments.
    Only allowed before any matches have been scheduled.
    """
    matches_df = load_sheet("Matches")
    if not matches_df.empty:
        raise RuntimeError(
            "Cannot reset teams after matches have been scheduled."
        )

    # Clear Teams sheet
    save_sheet("Teams", pd.DataFrame(columns=[
        "team_id", "team_name", "avg_skill", "wins", "losses", "is_eliminated"
    ]))

    # Clear team_id on all players
    players_df = load_sheet("Players")
    if not players_df.empty:
        players_df["team_id"] = None
        save_sheet("Players", players_df)


def get_all_teams() -> pd.DataFrame:
    """Return all teams as a DataFrame."""
    return load_sheet("Teams")


def get_team_players(team_id: int) -> pd.DataFrame:
    """Return the two players belonging to a team."""
    players_df = load_sheet("Players")
    if players_df.empty:
        return players_df
    return players_df[players_df["team_id"] == team_id].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num_to_letter(n: int) -> str:
    """0 → A, 1 → B, … 25 → Z, 26 → AA, etc."""
    result = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result
