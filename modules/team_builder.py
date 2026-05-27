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


def get_default_pairing(players_df: pd.DataFrame) -> list:
    """Return the default balanced pairing as a list of (player_id_1, player_id_2) tuples.

    Uses the sorted-interleaving algorithm: sort by skill descending,
    then pair rank-1 with rank-N, rank-2 with rank-(N-1), etc.
    """
    sorted_p = (
        players_df
        .sort_values("skill_rating", ascending=False)
        .reset_index(drop=True)
    )
    n = len(sorted_p)
    return [
        (int(sorted_p.iloc[i]["player_id"]), int(sorted_p.iloc[n - 1 - i]["player_id"]))
        for i in range(n // 2)
    ]


def build_balanced_teams(custom_pairing: list | None = None) -> pd.DataFrame:
    """
    Read players from the Players sheet, run the pairing algorithm,
    create Team records, assign player team_ids, and save both sheets.
    Returns the Teams DataFrame.

    Pass *custom_pairing* as a list of (player_id_1, player_id_2) tuples to
    override the default balanced algorithm (e.g. after manual swaps in the UI).

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

    players_map = {int(row["player_id"]): row for _, row in players_df.iterrows()}

    if custom_pairing is not None:
        pairing = [(int(a), int(b)) for a, b in custom_pairing]
        all_ids = set(players_map.keys())
        for pid1, pid2 in pairing:
            if pid1 not in all_ids or pid2 not in all_ids:
                raise ValueError("Custom pairing references an unknown player ID.")
    else:
        pairing = get_default_pairing(players_df)

    teams = []
    for i, (pid1, pid2) in enumerate(pairing):
        p1 = players_map[pid1]
        p2 = players_map[pid2]
        avg = round((float(p1["skill_rating"]) + float(p2["skill_rating"])) / 2, 2)
        team_id = get_next_id("Teams", "team_id") + i
        teams.append({
            "team_id":       team_id,
            "team_name":     f"Team {_num_to_letter(i)}",
            "avg_skill":     avg,
            "wins":          0,
            "losses":        0,
            "is_eliminated": False,
        })

    teams_df = pd.DataFrame(teams)
    save_sheet("Teams", teams_df)

    # Assign team_ids back to players (bulk update)
    players_copy = players_df.copy()
    for team, (pid1, pid2) in zip(teams, pairing):
        players_copy.loc[players_copy["player_id"] == pid1, "team_id"] = team["team_id"]
        players_copy.loc[players_copy["player_id"] == pid2, "team_id"] = team["team_id"]

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
